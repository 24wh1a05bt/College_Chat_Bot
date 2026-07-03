# BVRIT College FAQ Chatbot

RAG chatbot grounded in `data/college_website.docx`, built with Streamlit,
ChromaDB, and OpenRouter. See **[spec.md](spec.md)** for the full technical
design and rationale.

## Quickstart

```bash
# 1. Configure secrets
cp .env.example .env
# then edit .env and set OPENROUTER_API_KEY

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your document
mkdir -p data
cp /path/to/college_website.docx data/college_website.docx

# 4. Build the vector index
python -m src.ingest --rebuild

# 5. Launch the chat UI
streamlit run app.py

# 6. (Optional) Run the full 8-dimension evaluation suite
python run_evaluation.py
# results appear in eval_results/ and on the "Evaluation Dashboard" page
```

## Project layout

```
app.py                          Streamlit chat UI (Phase 4)
pages/1_Evaluation_Dashboard.py Evaluation report dashboard
run_evaluation.py               Orchestrates the full Phase 5 pipeline
src/
  config.py                     All settings (.env-driven)
  llm_client.py                 OpenRouter chat + embeddings wrapper
  embeddings.py                 Chroma embedding function (OpenRouter-backed)
  ingest.py                     Phase 1 — load, chunk, embed, index
  rag_chain.py                  Phase 2/3 — retrieval + grounded generation
  test_generator.py             Phase 5 Step A — LLM-generated test cases
  test_runner.py                Phase 5 Step B — run cases against chatbot
  judge.py                      Phase 5 Step C — LLM-as-judge scoring
  ragas_eval.py                 Phase 5 Dim 08 — RAGAS metrics
  report.py                     Phase 5 Step D — evaluation report
data/                           Put college_website.docx here (git-ignored content)
chroma_db/                      Persistent vector store (git-ignored)
eval_results/                   Generated test cases + reports (git-ignored)
```
