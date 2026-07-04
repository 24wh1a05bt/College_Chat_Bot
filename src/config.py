"""
Central configuration for the College FAQ Chatbot.
All values are overridable via environment variables / .env
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Paths -------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DOCX_PATH = Path(os.getenv("DOCX_PATH", DATA_DIR / "college_website.docx"))
IMAGES_DIR = Path(os.getenv("IMAGES_DIR", DATA_DIR / "images"))
PERSIST_DIR = str(BASE_DIR / os.getenv("CHROMA_DIR", "chroma_db"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "college_faq")
EVAL_DIR = BASE_DIR / "eval_results"

# --- OpenRouter ----------------------------------------------------------
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Models (all routed through OpenRouter). Keep generation and judge models
# different to avoid self-bias when the judge scores the chatbot's own output.
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "openai/gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "openai/gpt-4o")
TEST_GEN_MODEL = os.getenv("TEST_GEN_MODEL", "openai/gpt-4o")

# OpenRouter attribution headers (optional but recommended by OpenRouter)
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "http://localhost:8501")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "College FAQ Chatbot")

# --- Chunking ------------------------------------------------------------
# Section-aware splitting: the document has clear H1/H2 headings, so we first
# split by heading, then run a RecursiveCharacterTextSplitter *within* each
# section so a chunk never straddles two unrelated sections.
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))      # characters
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))  # characters

# --- Retrieval -------------------------------------------------------------
TOP_K = int(os.getenv("TOP_K", "5"))

# --- Evaluation ------------------------------------------------------------
PERFORMANCE_SLA_SECONDS = float(os.getenv("PERFORMANCE_SLA_SECONDS", "10"))

# Sections present in the source document - used to power the sidebar filter.
# Kept here as a fallback; ingest.py also derives this dynamically from the doc.
KNOWN_SECTIONS = [
    "About BVRIT",
    "Departments",
    "Admissions",
    "Fee Structure",
    "Placements",
    "Campus & Facilities",
    "Faculty",
    "Contact",
]

FALLBACK_CONTACT = os.getenv(
    "FALLBACK_CONTACT",
    "BVRIT Admissions Office — admissions@bvrit.ac.in — https://bvrit.ac.in",
)