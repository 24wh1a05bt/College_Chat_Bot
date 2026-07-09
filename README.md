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
app.py                          Streamlit chat UI

run_evaluation.py               Orchestrates the complete evaluation pipeline

enhance_docx.py                 Enhances/cleans the source DOCX
diagnose_images.py              Utility for debugging extracted images
scraper.py                      Website scraping utility

src/
├── config.py                   Application configuration (.env-driven)
├── llm_client.py               OpenRouter LLM & embedding client
├── embeddings.py               Embedding generation and vector store interface
├── ingest.py                   Document ingestion and Chroma indexing
├── rag_chain.py                RAG retrieval and response generation
├── memory.py                   Conversation memory & user profile management
├── profile_schema.py           User profile schema/models
├── tools.py                    Custom tools used by the chatbot
├── test_generator.py           Generate evaluation test cases
├── test_runner.py              Execute generated test cases
├── judge.py                    LLM-as-a-Judge evaluation
├── ragas_eval.py               RAGAS evaluation metrics
├── report.py                   Generate evaluation reports
└── __init__.py

data/
├── college_website.docx        Source knowledge document (tracked)
└── images/                     Extracted images (git-ignored)

chroma_db/                      Chroma vector database (git-ignored)

eval_results/                   Generated evaluation reports (git-ignored)

requirements.txt                Project dependencies
README.md                       Project documentation
spec.md                         Project specification
task_progress.md                Development progress log

test_memory.py                  Memory module tests
test_retrieval.py               Retrieval tests
test_retrieval2.py              Additional retrieval tests

.env                            Environment variables (git-ignored)
.gitignore                      Git ignore rules
```
