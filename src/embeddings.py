"""
ChromaDB-compatible embedding function that calls OpenRouter's
text-embedding-3-small endpoint. Using the *same* function for indexing
and querying is critical - Chroma stores the function name in its
metadata and will warn if it changes between runs.
"""
from chromadb import Documents, EmbeddingFunction, Embeddings

from src import config
from src.llm_client import embed_texts


class OpenRouterEmbeddingFunction(EmbeddingFunction):
    def __init__(self, model: str = None):
        self.model = model or config.EMBEDDING_MODEL

    def __call__(self, input: Documents) -> Embeddings:
        # OpenRouter/OpenAI embedding endpoints accept batches directly.
        return embed_texts(list(input), model=self.model)

    def name(self) -> str:
        return f"openrouter-{self.model}"
