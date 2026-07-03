# College FAQ Chatbot — Technical Spec

RAG-powered FAQ chatbot for BVRIT, grounded in `data/college_website.docx`,
served through Streamlit, with an 8-dimension automated evaluation suite.
All LLM and embedding calls are routed through **OpenRouter**.

## 1. Architecture

```
data/college_website.docx
        │  (python-docx: split by heading)
        ▼
   Section objects
        │  (RecursiveCharacterTextSplitter, per section)
        ▼
   Chunks + metadata {source, section, section_chunk_index, page}
        │  (OpenRouter: text-embedding-3-small)
        ▼
   ChromaDB (persistent, local, ./chroma_db)
        │  (query-time similarity search, optional section filter)
        ▼
   Top-k chunks ──► grounding prompt ──► OpenRouter chat model ──► answer + citations
```

Streamlit (`app.py`) is the only user-facing surface for chat. A second
page (`pages/1_Evaluation_Dashboard.py`) renders the evaluation report
produced offline by `run_evaluation.py`.

## 2. Component decisions

| Component | Choice | Why |
|---|---|---|
| Orchestration | Hand-rolled (no LangChain retrieval chain) + `langchain-text-splitters` for chunking, `langchain-openai` for RAGAS's internal LLM/embedding calls | Keeps the retrieve/generate loop transparent and easy to instrument for latency + citation metadata; still reuses LangChain's well-tested splitter instead of reinventing it. |
| Document loader | `python-docx`, custom heading-aware parser | `Docx2txtLoader` flattens the whole doc into one string and loses heading structure, which we need for the `section` metadata field and the section filter. |
| Text splitter | `RecursiveCharacterTextSplitter`, run **per section**, not globally | The document has clear H1/H2 headings (see build brief §Phase 1). Splitting per section guarantees no chunk mixes two unrelated topics (e.g. Fees + Placements), which is the #1 driver of low RAGAS Context Precision. |
| Chunk size / overlap | 800 chars / 150 chars overlap (default, `.env`-tunable) | Fee tables and department lists are dense with short factual lines; 800 chars (~150–200 words) keeps a chunk to roughly one sub-topic while overlap preserves boundary sentences (e.g. a heading immediately followed by its first fact). |
| Embedding model | `text-embedding-3-small` via OpenRouter (1536-dim) | Matches the build brief's recommendation; same model is used for indexing and querying (enforced by `src/embeddings.py`). |
| Vector DB | ChromaDB, `PersistentClient` at `./chroma_db` | Local, no server, persists across restarts. Chunk count is verified via `collection.count()` in the sidebar. |
| Generation LLM | `openai/gpt-4o-mini` via OpenRouter | Fast, cheap, strong instruction following per the brief; swappable via `GENERATION_MODEL`. |
| Judge LLM | `anthropic/claude-3.5-sonnet` via OpenRouter | Deliberately different from the generation model to avoid self-bias when judging the chatbot's own answers. |
| Test-generator LLM | `openai/gpt-4o` via OpenRouter | Higher-quality model for producing accurate test cases + expected answers, per the brief's "use a strong model" guidance. |
| UI | Streamlit, `st.chat_input` / `st.chat_message`, multipage app | Matches the brief's recommended stack; the dashboard is a separate page under `pages/`. |
| Evaluation | Custom 3-LLM pipeline (generator → chatbot → judge) + RAGAS for dimension 08 | Matches the brief's "three-LLM pattern" exactly. |

## 3. Metadata & citations

Every chunk carries:
- `source`: the docx filename
- `section`: the nearest heading text (e.g. "Fee Structure")
- `section_chunk_index`: position within that section
- `page`: **approximated** from a running word count (400 words/page).
  `.docx` files have no fixed pagination in their XML — real page numbers
  only exist once a specific renderer paginates the file. This is a known,
  documented limitation; if exact page numbers are required, export the
  source to PDF first and switch `ingest.py` to `PyPDFLoader`, which
  provides true page metadata.

Citations are rendered as `[Section Name, Page N]`, enforced by the system
prompt in `src/rag_chain.py`.

## 4. Grounding prompt (Phase 3 requirements)

`SYSTEM_PROMPT` in `src/rag_chain.py` implements all five required elements:
1. **Role** — "BVRIT College Information Assistant."
2. **Grounding rule** — answer only from the provided context, never from
   training knowledge.
3. **Citation format** — `[Section Name, Page N]`, multiple citations
   allowed per sentence.
4. **Refusal instruction** — fixed refusal string that includes
   `FALLBACK_CONTACT` (configurable in `.env`).
5. **Conflict handling** — explicit instruction to surface both values and
   flag the discrepancy when sections disagree.

## 5. Retrieval

- Default `top_k = 5` (brief's recommended starting point), adjustable in
  the sidebar (1–10).
- Optional metadata filter on `section` (Chroma `where` clause), exposed as
  a sidebar dropdown populated dynamically from indexed sections.
- If Chroma returns zero chunks (e.g. filter excludes everything), the app
  returns the fixed refusal message instead of calling the LLM — avoids
  wasting a generation call on an empty context.

## 6. Evaluation pipeline (Phase 5)

Orchestrated end-to-end by `run_evaluation.py`:

1. **`src/test_generator.py`** — LLM #1 reads the grounding document and
   emits `eval_results/test_cases.json`: 20 cases across all 8 dimensions
   (3/3/2/2/3/2/2/3), each with `id`, `dimension`, `question` (or `turns`
   for the context dimension), `expected_answer`, `pass_fail_criteria`.
2. **`src/test_runner.py`** — LLM #2 (the chatbot itself) answers every
   case, capturing actual answer, retrieved chunks, and latency into
   `eval_results/run_results.json`.
3. **`src/judge.py`** — LLM #3 compares expected vs actual per dimension
   with dimension-specific criteria (see `JUDGE_INSTRUCTIONS`); Dimension
   06 (Performance) is scored numerically against `PERFORMANCE_SLA_SECONDS`
   instead of by an LLM. Output: `eval_results/judged_results.json`.
4. **`src/ragas_eval.py`** — Dimension 08 is scored programmatically with
   the `ragas` library (faithfulness, answer relevancy, context precision,
   context recall), using the judge model + embedding model via OpenRouter.
   Output: `eval_results/ragas_scores.json`.
5. **`src/report.py`** — compiles everything into
   `eval_results/evaluation_report.json` (+ a Markdown copy): summary
   counts, per-dimension pass/fail, weakest dimension, a rule-based
   recommended fix per dimension, and the RAGAS score summary.

The Streamlit dashboard (`pages/1_Evaluation_Dashboard.py`) reads
`evaluation_report.json` directly — it does not call any LLM at render
time, so it's fast and reproducible from a saved report.

### Pass/fail semantics
- LLM-judged dimensions: judge returns `pass` / `fail` / `warning` with a
  `reason`, `root_cause`, and `suggested_fix`.
- Performance: numeric SLA check.
- RAGAS: a case is marked `pass` only if **all four** RAGAS metrics
  average ≥ 0.7 across the RAGAS test cases (threshold configurable in
  `src/report.py`).

## 7. Setup

```bash
cp .env.example .env          # fill in OPENROUTER_API_KEY
pip install -r requirements.txt
mkdir -p data && cp /path/to/college_website.docx data/

python -m src.ingest --rebuild   # Phase 1: build the index
streamlit run app.py             # Phase 4: chat UI

python run_evaluation.py         # Phase 5: full evaluation pipeline
# then open the "Evaluation Dashboard" page inside the running Streamlit app
```

## 8. Known limitations

- Page numbers are approximate (see §3) since `.docx` has no fixed
  pagination — switch to a PDF source + `PyPDFLoader` for exact pages.
- The judge and RAGAS calls assume OpenRouter exposes an OpenAI-compatible
  `/embeddings` endpoint for the chosen embedding model; not all OpenRouter
  models support embeddings — confirm `EMBEDDING_MODEL` does before
  running ingestion.
- Conversation history sent to the generation model is capped at the last
  3 turns (`src/rag_chain.py`) to control token usage; this is sufficient
  for the Phase 5 two-turn context test but may need widening for longer
  multi-turn stretch-goal testing.
