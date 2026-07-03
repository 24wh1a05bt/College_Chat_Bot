"""
College FAQ Chatbot - Streamlit chat UI.

Run with:
    streamlit run app.py
"""
import streamlit as st

from src import config
from src.ingest import build_index, get_collection, list_sections
from src.rag_chain import answer

st.set_page_config(page_title="BVRIT FAQ Chatbot", page_icon="🎓", layout="wide")

# --- Session state ---------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []  # [{role, content, citations, refused, latency, images}]


def render_images(image_filenames: list[str]) -> None:
    """Show extracted document images (from config.IMAGES_DIR) in a grid."""
    existing = [f for f in image_filenames if (config.IMAGES_DIR / f).exists()]
    if not existing:
        return
    with st.expander(f"🖼️ Related images ({len(existing)})", expanded=True):
        cols = st.columns(min(3, len(existing)))
        for i, filename in enumerate(existing):
            with cols[i % len(cols)]:
                st.image(str(config.IMAGES_DIR / filename), use_container_width=True)

# --- Sidebar -----------------------------------------------------------
with st.sidebar:
    st.title("🎓 BVRIT FAQ Chatbot")
    st.caption("RAG-powered · grounded in the official college document")

    st.subheader("Knowledge base")
    doc_exists = config.DOCX_PATH.exists()
    if doc_exists:
        try:
            collection = get_collection()
            chunk_count = collection.count()
        except Exception as e:
            chunk_count = 0
            st.error(f"Index error: {e}")

        st.markdown(f"**Document:** `{config.DOCX_PATH.name}`")
        if chunk_count > 0:
            st.markdown(f"**Status:** 🟢 Indexed ({chunk_count} chunks)")
        else:
            st.markdown("**Status:** 🟡 Not indexed yet")
            if st.button("Build index now"):
                with st.spinner("Chunking, embedding, and indexing..."):
                    build_index(rebuild=False)
                st.rerun()

        if st.button("🔁 Rebuild index"):
            with st.spinner("Re-embedding all chunks..."):
                build_index(rebuild=True)
            st.rerun()
    else:
        st.warning(
            f"Document not found at `{config.DOCX_PATH}`.\n\n"
            "Place your college_website.docx in the `data/` folder."
        )
        chunk_count = 0

    st.divider()
    st.subheader("Retrieval settings")
    st.markdown(f"- Chunk size: **{config.CHUNK_SIZE}** chars")
    st.markdown(f"- Chunk overlap: **{config.CHUNK_OVERLAP}** chars")
    top_k = st.slider("Top-k chunks", min_value=1, max_value=10, value=config.TOP_K)

    section_options = ["All sections"] + (list_sections() if chunk_count else config.KNOWN_SECTIONS)
    section_filter = st.selectbox("Section filter", section_options)

    st.divider()
    st.subheader("Models (via OpenRouter)")
    st.caption(f"Generation: `{config.GENERATION_MODEL}`")
    st.caption(f"Embeddings: `{config.EMBEDDING_MODEL}`")

    if st.button("🗑️ Clear conversation"):
        st.session_state.messages = []
        st.rerun()

# --- Main chat area ------------------------------------------------------
st.header("Ask about BVRIT")
st.caption("Answers are grounded strictly in the official college document, with citations.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            if msg.get("refused"):
                st.markdown(
                    "<span style='background-color:#fff3cd;color:#7a5c00;"
                    "padding:2px 10px;border-radius:12px;font-size:0.8em;"
                    "font-weight:600;'>🚫 REFUSED — not in knowledge base</span>",
                    unsafe_allow_html=True,
                )
            if msg.get("citations"):
                with st.expander("📎 Sources"):
                    for c in msg["citations"]:
                        st.markdown(f"**[{c['section']}, Page {c['page']}]**")
                        st.caption(c["text"][:300] + ("..." if len(c["text"]) > 300 else ""))
            if msg.get("images"):
                render_images(msg["images"])
            if msg.get("latency") is not None:
                st.caption(f"⏱ {msg['latency']:.2f}s")

query = st.chat_input("Ask a question about BVRIT (admissions, fees, placements, ...)")

if query:
    if not config.DOCX_PATH.exists() or chunk_count == 0:
        st.error("The knowledge base isn't indexed yet. Use the sidebar to build the index first.")
    else:
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)

        with st.chat_message("assistant"):
            with st.spinner("Retrieving and generating..."):
                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages[:-1]
                ]
                result = answer(
                    query,
                    chat_history=history,
                    top_k=top_k,
                    section_filter=section_filter,
                )
            st.markdown(result.answer)
            if result.refused:
                st.markdown(
                    "<span style='background-color:#fff3cd;color:#7a5c00;"
                    "padding:2px 10px;border-radius:12px;font-size:0.8em;"
                    "font-weight:600;'>🚫 REFUSED — not in knowledge base</span>",
                    unsafe_allow_html=True,
                )
            citations = [
                {"section": c.section, "page": c.page, "text": c.text} for c in result.chunks
            ]
            if citations:
                with st.expander("📎 Sources"):
                    for c in citations:
                        st.markdown(f"**[{c['section']}, Page {c['page']}]**")
                        st.caption(c["text"][:300] + ("..." if len(c["text"]) > 300 else ""))
            if result.images:
                render_images(result.images)
            st.caption(f"⏱ {result.latency_seconds:.2f}s")

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": result.answer,
                "citations": citations,
                "refused": result.refused,
                "latency": result.latency_seconds,
                "images": result.images,
            }
        )