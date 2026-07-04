"""
Phase 2 - Retrieval and Phase 3 - Grounded generation.

retrieve()   -> queries Chroma, returns ranked chunks + metadata
answer()     -> builds the grounding prompt, calls the generation LLM,
                and returns the answer text together with the chunks used
                (needed downstream for citations and RAGAS scoring).
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from src import config
from src.ingest import get_collection
from src.llm_client import chat_completion

SYSTEM_PROMPT = """You are the BVRIT College Information Assistant, an official
FAQ chatbot for BVRIT (B V Raju Institute of Technology). You help prospective
and current students, parents, and staff with factual questions about the
college.

GROUNDING RULE
Answer ONLY using the CONTEXT provided below. Never use your own training
knowledge about BVRIT or any other college, even if you believe you know the
answer. If the context does not contain the information needed to answer,
say so - do not guess, estimate, or invent facts (fee amounts, dates,
percentages, names, etc. must come verbatim or near-verbatim from the
context).

CITATION FORMAT
Every factual claim must be followed by a citation in the exact format:
[Section Name, Page N]
Use the "section" and "page" values attached to each context chunk below.
If a single sentence draws on multiple chunks, cite all of them, e.g.
[Admissions, Page 2][Fee Structure, Page 3].

REFUSAL INSTRUCTION
If the answer is not contained in the context, reply with:
"I don't have that information in the BVRIT knowledge base I was given.
For an accurate answer, please contact {fallback_contact}."
Do not apologize excessively or speculate further after the refusal.

CONFLICT HANDLING
If two chunks in the context give different information on the same fact,
present both values, cite each separately, and explicitly note the
discrepancy (e.g. "Two sections of the source document give different
figures here: ... This should be verified with the college.").

IMAGE HANDLING
Some context chunks have images attached (photos, logos, campus pictures).
You never see the image bytes yourself and you never receive a filename in
the context - so never invent or print anything that looks like a filename
(e.g. "image-003.png"). If the user asks to see a photo/picture/image and
one is available for the relevant section, simply say something like "Here
is the photo from that section" and let the interface display it - do not
describe pixel content you have not actually seen. If none is available,
say so plainly instead of guessing.

STYLE
Be concise, factual, and neutral. Do not make promises about individual
outcomes (admission chances, placement guarantees, scholarship eligibility).
Do not give medical, legal, or financial advice.
""".format(fallback_contact=config.FALLBACK_CONTACT)

# Keywords used to detect an explicit request to *see* an image, rather than
# just a question that happens to mention a photo-worthy topic (e.g. "campus
# facilities" alone shouldn't trigger an image; "show me a photo of the
# campus" should).
_IMAGE_INTENT_RE = re.compile(
    r"\b(show|see|view|display)\b.{0,25}\b(image|photo|picture|pic|logo|snapshot)s?\b"
    r"|\b(image|photo|picture|pic|logo)s?\b.{0,25}\b(of|for)\b",
    re.IGNORECASE,
)


def wants_image(query: str) -> bool:
    """True only when the user explicitly asked to see an image."""
    return bool(_IMAGE_INTENT_RE.search(query))


@dataclass
class RetrievedChunk:
    text: str
    section: str
    page: int
    source: str
    distance: float
    images: list[dict] = field(default_factory=list)  # [{"filename","caption"}]


@dataclass
class RAGResponse:
    answer: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    latency_seconds: float = 0.0
    refused: bool = False
    images: list[dict] = field(default_factory=list)  # only populated if explicitly requested


def retrieve(query: str, top_k: int = None, section_filter: str | None = None) -> list[RetrievedChunk]:
    collection = get_collection()
    top_k = top_k or config.TOP_K

    where = None
    if section_filter and section_filter != "All sections":
        where = {"section": section_filter}

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        where=where,
    )

    chunks = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        raw_images = meta.get("images", "") or ""
        images = []
        if raw_images:
            try:
                parsed = json.loads(raw_images)
            except json.JSONDecodeError:
                parsed = []
            # Normalize whatever shape ended up in metadata (a stale/rebuilt
            # index could have a single dict, a bare filename string, or a
            # proper list of dicts) into a consistent list[dict].
            if isinstance(parsed, dict):
                parsed = [parsed]
            elif isinstance(parsed, str):
                parsed = [{"filename": parsed, "caption": ""}]
            elif not isinstance(parsed, list):
                parsed = []
            for entry in parsed:
                if isinstance(entry, dict) and entry.get("filename"):
                    images.append({"filename": entry["filename"], "caption": entry.get("caption", "")})
                elif isinstance(entry, str) and entry:
                    images.append({"filename": entry, "caption": ""})
        chunks.append(
            RetrievedChunk(
                text=doc,
                section=meta.get("section", "Unknown"),
                page=meta.get("page", 0),
                source=meta.get("source", ""),
                distance=dist,
                images=images,
            )
        )
    return chunks


def _format_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for c in chunks:
        blocks.append(f"[{c.section}, Page {c.page}]\n{c.text}")
    return "\n\n---\n\n".join(blocks)


def answer(
    query: str,
    chat_history: list[dict] | None = None,
    top_k: int = None,
    section_filter: str | None = None,
) -> RAGResponse:
    start = time.time()
    chunks = retrieve(query, top_k=top_k, section_filter=section_filter)

    if not chunks:
        latency = time.time() - start
        return RAGResponse(
            answer=(
                "I don't have that information in the BVRIT knowledge base "
                f"I was given. For an accurate answer, please contact "
                f"{config.FALLBACK_CONTACT}."
            ),
            chunks=[],
            latency_seconds=latency,
            refused=True,
        )

    context = _format_context(chunks)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if chat_history:
        messages.extend(chat_history[-6:])  # keep last 3 turns for context
    messages.append(
        {
            "role": "user",
            "content": f"CONTEXT:\n{context}\n\nQUESTION: {query}",
        }
    )

    text = chat_completion(messages, model=config.GENERATION_MODEL, temperature=0.1, max_tokens=700)
    latency = time.time() - start

    refused = "don't have that information" in text.lower() or "contact " in text.lower()[:200] and "i don't have" in text.lower()

    images: list[dict] = []
    if wants_image(query) and not refused:
        seen = set()
        for c in chunks:
            for img in c.images:
                if img["filename"] in seen:
                    continue
                seen.add(img["filename"])
                images.append(
                    {
                        "filename": img["filename"],
                        "caption": img.get("caption", ""),
                        "section": c.section,
                        "path": str(config.IMAGES_DIR / img["filename"]),
                    }
                )

    return RAGResponse(answer=text, chunks=chunks, latency_seconds=latency, refused=refused, images=images)