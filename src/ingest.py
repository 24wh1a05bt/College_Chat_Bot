"""
Phase 1 - Ingest and index.

Loads data/college_website.docx, splits it by heading (so a chunk never
straddles two unrelated sections), then further splits long sections with
a RecursiveCharacterTextSplitter, embeds every chunk via OpenRouter, and
persists everything to a local ChromaDB collection.

Images embedded in the .docx are also extracted here: each image is saved
to disk under config.IMAGES_DIR and associated with whichever section it
appeared in, so the chat UI can show relevant images alongside an answer.

Run directly to (re)build the index:
    python -m src.ingest --rebuild
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field

import chromadb
from docx import Document as DocxDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src import config
from src.embeddings import OpenRouterEmbeddingFunction

# Word-per-page approximation used only to produce a human-friendly citation.
# A .docx has no fixed pagination in its XML (pagination is computed at
# render time), so we approximate "page N" from a running word count.
# This is documented in spec.md as a known limitation.
WORDS_PER_PAGE = 400

# XML namespaces needed to find inline images (<a:blip r:embed="rIdX"/>)
# inside a paragraph's XML.
_DRAWING_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
_R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


@dataclass
class Section:
    heading: str
    level: int
    paragraphs: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)  # filenames, relative to IMAGES_DIR

    @property
    def text(self) -> str:
        return "\n".join(p for p in self.paragraphs if p.strip())


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40] or "section"


def _extract_images_from_paragraph(doc: DocxDocument, para, section_slug: str, counter: list[int]) -> list[str]:
    """Pull every inline image out of a paragraph and save it to IMAGES_DIR.

    Returns the list of saved filenames (relative to config.IMAGES_DIR).
    `counter` is a single-element list used as a mutable running index so
    filenames stay unique and stable across the whole document.
    """
    saved = []
    blips = para._p.findall(".//a:blip", _DRAWING_NS)
    for blip in blips:
        rid = blip.get(_R_EMBED)
        if not rid:
            continue
        try:
            image_part = doc.part.related_parts[rid]
        except KeyError:
            continue

        content_type = image_part.content_type or "image/png"
        ext = content_type.split("/")[-1].lower()
        ext = "jpg" if ext == "jpeg" else ext
        ext = re.sub(r"[^a-z0-9]", "", ext) or "png"

        counter[0] += 1
        filename = f"{section_slug}-{counter[0]:03d}.{ext}"
        out_path = config.IMAGES_DIR / filename
        out_path.write_bytes(image_part.blob)
        saved.append(filename)

    return saved


def parse_sections(docx_path) -> list[Section]:
    """Walk the document and group paragraphs (and images) under their nearest heading."""
    doc = DocxDocument(str(docx_path))
    config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    sections: list[Section] = []
    current = Section(heading="Preamble", level=0)
    image_counter = [0]

    for para in doc.paragraphs:
        style_name = (para.style.name or "").lower()
        text = para.text.strip()

        # Images can appear in otherwise-empty paragraphs, so check for them
        # even when there's no text to process.
        section_slug = _slugify(current.heading)
        images = _extract_images_from_paragraph(doc, para, section_slug, image_counter)
        if images:
            current.images.extend(images)

        if not text:
            continue

        if style_name.startswith("heading") or style_name in ("title",):
            # Start a new section on every heading paragraph.
            if current.text or current.images:
                sections.append(current)
            level = 1
            if style_name.startswith("heading"):
                digits = "".join(ch for ch in style_name if ch.isdigit())
                level = int(digits) if digits else 1
            current = Section(heading=text, level=level)
        else:
            current.paragraphs.append(text)

    if current.text or current.images:
        sections.append(current)

    # Drop an empty leading "Preamble" section if nothing landed in it.
    return [s for s in sections if s.text.strip() or s.images]


def chunk_sections(sections: list[Section]) -> list[dict]:
    """Split each section into overlapping chunks, carrying rich metadata."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []
    running_words = 0
    chunk_id = 0

    for section in sections:
        section_chunks = splitter.split_text(section.text) if section.text else [""]
        for idx, chunk_text in enumerate(section_chunks):
            if not chunk_text.strip() and not section.images:
                continue
            running_words += len(chunk_text.split())
            page = max(1, running_words // WORDS_PER_PAGE + 1)
            chunks.append(
                {
                    "id": f"chunk-{chunk_id:04d}",
                    "text": chunk_text or f"[{section.heading}]",
                    "metadata": {
                        "source": config.DOCX_PATH.name,
                        "section": section.heading,
                        "section_chunk_index": idx,
                        "page": page,
                        # Chroma metadata values must be scalar, so the image
                        # list is JSON-encoded and decoded again on retrieval.
                        "images": json.dumps(section.images),
                    },
                }
            )
            chunk_id += 1

    return chunks


def build_index(rebuild: bool = False) -> chromadb.Collection:
    if not config.DOCX_PATH.exists():
        sys.exit(
            f"Could not find {config.DOCX_PATH}. Place your college "
            f"document there (or set DOCX_PATH in .env)."
        )

    client = chromadb.PersistentClient(path=config.PERSIST_DIR)
    embed_fn = OpenRouterEmbeddingFunction()

    if rebuild:
        try:
            client.delete_collection(config.COLLECTION_NAME)
        except Exception:
            pass
        # Clear previously extracted images so stale/renamed ones don't linger.
        if config.IMAGES_DIR.exists():
            for f in config.IMAGES_DIR.glob("*"):
                f.unlink()

    collection = client.get_or_create_collection(
        name=config.COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )

    if collection.count() > 0 and not rebuild:
        print(f"Index already has {collection.count()} chunks. Use --rebuild to re-index.")
        return collection

    sections = parse_sections(config.DOCX_PATH)
    chunks = chunk_sections(sections)

    if not chunks:
        sys.exit("No chunkable content found in the document.")

    collection.add(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )

    total_images = len({img for s in sections for img in s.images})
    print(f"Indexed {len(chunks)} chunks from {len(sections)} sections "
          f"({total_images} images extracted) into "
          f"'{config.COLLECTION_NAME}' at {config.PERSIST_DIR}")
    return collection


def get_collection() -> chromadb.Collection:
    """Open the existing collection without re-embedding (used by the app)."""
    client = chromadb.PersistentClient(path=config.PERSIST_DIR)
    return client.get_or_create_collection(
        name=config.COLLECTION_NAME,
        embedding_function=OpenRouterEmbeddingFunction(),
        metadata={"hnsw:space": "cosine"},
    )


def list_sections() -> list[str]:
    """Distinct section names currently in the index, for the sidebar filter."""
    collection = get_collection()
    if collection.count() == 0:
        return config.KNOWN_SECTIONS
    got = collection.get(include=["metadatas"])
    sections = sorted({m["section"] for m in got["metadatas"]})
    return sections


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true", help="Force re-indexing")
    args = parser.parse_args()
    build_index(rebuild=args.rebuild)
