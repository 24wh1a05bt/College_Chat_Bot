"""
College FAQ Chatbot - Streamlit chat UI.

Run with:
    streamlit run app.py
"""
import html
import os

import streamlit as st

from src import config
from src.ingest import build_index, get_collection, list_sections
from src.rag_chain import answer

st.set_page_config(
    page_title="BVRIT FAQ Assistant",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Session state ---------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []  # [{role, content, citations, refused, latency}]


# --- Design system ----------------------------------------------------------
# A quiet, institutional palette (deep navy + academic gold on a cool paper
# background) so the chatbot reads as an official record-lookup tool rather
# than a generic chat demo. Every custom visual below is plain HTML/CSS
# rendered through st.markdown, so it can't be knocked out of alignment by
# Streamlit's internal class names changing between versions.
def _inject_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');

        :root{
            --navy-900:#0B1F3A;
            --navy-700:#15335C;
            --navy-500:#2C4E82;
            --gold-500:#C69A2E;
            --gold-100:#F5E9C9;
            --paper-50:#F5F7FA;
            --ink-900:#182233;
            --ink-500:#5B6B82;
            --border:#DCE3EC;
            --success-600:#1F7A4D;
            --success-50:#E7F5EC;
            --warn-600:#A9660A;
            --warn-50:#FBF0DE;
            --danger-600:#B3261E;
            --danger-50:#FCE8E6;
        }

        .stApp{ background:var(--paper-50); }
        html, body, [class*="css"]{ font-family:'Inter',sans-serif; color:var(--ink-900); }
        h1,h2,h3{ font-family:'Source Serif 4',serif; }

        /* ---- Sidebar ---- */
        section[data-testid="stSidebar"]{
            background:linear-gradient(180deg,var(--navy-900) 0%,var(--navy-700) 100%);
            border-right:1px solid var(--navy-900);
        }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] .stMarkdown,
        section[data-testid="stSidebar"] .stCaption{
            color:#E7ECF5 !important;
        }
        section[data-testid="stSidebar"] hr{ border-color:rgba(255,255,255,0.14); }
        section[data-testid="stSidebar"] .stButton>button{
            background:var(--gold-500);
            color:var(--navy-900);
            border:none;
            border-radius:8px;
            font-weight:600;
            width:100%;
        }
        section[data-testid="stSidebar"] .stButton>button:hover{
            background:#D9AE44;
            color:var(--navy-900);
        }

        /* ---- Sidebar brand block ---- */
        .brand-block{ padding:4px 0 18px 0; border-bottom:1px solid rgba(255,255,255,0.14); margin-bottom:16px; }
        .brand-crest{
            display:inline-flex; align-items:center; justify-content:center;
            width:40px; height:40px; border-radius:10px;
            background:var(--gold-500); color:var(--navy-900);
            font-size:20px; margin-bottom:10px;
        }
        .brand-name{ font-family:'Source Serif 4',serif; font-size:1.15rem; font-weight:700; color:#FFFFFF; line-height:1.25; }
        .brand-tagline{ font-size:0.78rem; color:#AFC0D9; letter-spacing:.02em; text-transform:uppercase; }

        .side-label{
            font-size:0.72rem; font-weight:600; letter-spacing:.06em; text-transform:uppercase;
            color:#9FB3CF !important; margin:2px 0 8px 0;
        }

        /* ---- Chips / badges ---- */
        .chip{
            display:inline-flex; align-items:center; gap:6px;
            padding:4px 10px; border-radius:999px; font-size:0.78rem; font-weight:600;
            border:1px solid transparent; white-space:nowrap;
        }
        .chip-dot{ width:7px; height:7px; border-radius:50%; display:inline-block; }
        .chip-success{ background:var(--success-50); color:var(--success-600); border-color:#CDE9D8; }
        .chip-success .chip-dot{ background:var(--success-600); }
        .chip-warn{ background:var(--warn-50); color:var(--warn-600); border-color:#F1DFB6; }
        .chip-warn .chip-dot{ background:var(--warn-600); }
        .chip-danger{ background:var(--danger-50); color:var(--danger-600); border-color:#F3C9C5; }
        .chip-danger .chip-dot{ background:var(--danger-600); }
        .chip-neutral{ background:rgba(255,255,255,0.10); color:#E7ECF5; border-color:rgba(255,255,255,0.18); }
        .chip-mono{ font-family:'IBM Plex Mono',monospace; font-weight:500; font-size:0.74rem; }

        /* ---- Hero header ---- */
        .hero{
            display:flex; align-items:center; gap:16px;
            background:#FFFFFF; border:1px solid var(--border); border-left:5px solid var(--gold-500);
            border-radius:12px; padding:18px 22px; margin-bottom:14px;
            box-shadow:0 1px 2px rgba(16,24,40,0.04);
        }
        .hero-icon{ font-size:2rem; line-height:1; }
        .hero-title{ font-family:'Source Serif 4',serif; font-weight:700; font-size:1.5rem; color:var(--navy-900); margin:0; }
        .hero-sub{ color:var(--ink-500); font-size:0.92rem; margin-top:2px; }

        .status-row{ display:flex; flex-wrap:wrap; gap:8px; margin:0 0 20px 2px; }
        .status-row .chip{ background:#FFFFFF; border:1px solid var(--border); color:var(--ink-900); }
        .status-row .chip-mono{ background:var(--navy-900); color:#F5E9C9; border-color:var(--navy-900); }

        /* ---- Chat bubbles (light-touch styling of stable Streamlit hooks) ---- */
        div[data-testid="stChatMessage"]{
            background:#FFFFFF;
            border:1px solid var(--border);
            border-radius:12px;
            padding:4px 6px;
            box-shadow:0 1px 2px rgba(16,24,40,0.03);
        }

        /* ---- Refusal / grounded badges above an answer ---- */
        .verdict-badge{
            display:inline-flex; align-items:center; gap:6px;
            padding:3px 11px; border-radius:999px; font-size:0.74rem; font-weight:700;
            letter-spacing:.02em; text-transform:uppercase; margin-bottom:8px;
        }
        .verdict-refused{ background:var(--warn-50); color:var(--warn-600); border:1px solid #F1DFB6; }
        .verdict-grounded{ background:var(--success-50); color:var(--success-600); border:1px solid #CDE9D8; }

        /* ---- Citation ledger cards ---- */
        .citation-card{
            border:1px solid var(--border); border-left:3px solid var(--navy-500);
            border-radius:8px; padding:10px 12px; margin-bottom:8px; background:#FAFBFD;
        }
        .citation-tag{
            display:inline-block; font-family:'IBM Plex Mono',monospace; font-size:0.72rem;
            font-weight:600; color:var(--navy-900); background:var(--gold-100);
            border-radius:5px; padding:2px 7px; margin-bottom:6px;
        }
        .citation-text{ font-size:0.86rem; color:var(--ink-900); font-style:italic; line-height:1.45; }

        .latency-tag{
            font-family:'IBM Plex Mono',monospace; font-size:0.76rem; color:var(--ink-500);
        }

        .footer-note{
            margin-top:28px; padding-top:14px; border-top:1px solid var(--border);
            color:var(--ink-500); font-size:0.8rem; text-align:center;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _chip(label: str, kind: str = "neutral", mono: bool = False) -> str:
    classes = f"chip chip-{kind}" + (" chip-mono" if mono else "")
    dot = '<span class="chip-dot"></span>' if kind in ("success", "warn", "danger") else ""
    return f'<span class="{classes}">{dot}{html.escape(label)}</span>'


def _verdict_badge(refused: bool) -> str:
    if refused:
        return '<span class="verdict-badge verdict-refused">🚫 Not in knowledge base</span>'
    return '<span class="verdict-badge verdict-grounded">✓ Grounded in source document</span>'


def _render_images(images: list[dict]) -> None:
    """Render images the user explicitly asked to see. Missing files are
    skipped quietly (e.g. the index was built before this feature existed
    and hasn't been rebuilt yet)."""
    available = [im for im in images if os.path.exists(im["path"])]
    if not available:
        return
    cols = st.columns(min(len(available), 3))
    for col, im in zip(cols * (len(available) // len(cols) + 1), available):
        with col:
            st.image(im["path"], caption=f"{im['section']}" + (f" — {im['caption']}" if im.get("caption") else ""))


def _citation_card(section: str, page: int, text: str, limit: int = 300) -> str:
    snippet = text[:limit] + ("…" if len(text) > limit else "")
    return (
        '<div class="citation-card">'
        f'<div class="citation-tag">{html.escape(section)} · P.{page}</div>'
        f'<div class="citation-text">“{html.escape(snippet)}”</div>'
        "</div>"
    )


_inject_css()

# --- Sidebar -----------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div class="brand-block">
            <div class="brand-crest">🎓</div>
            <div class="brand-name">BVRIT FAQ Assistant</div>
            <div class="brand-tagline">Retrieval-grounded · Official record</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="side-label">Knowledge base</div>', unsafe_allow_html=True)
    doc_exists = config.DOCX_PATH.exists()
    if doc_exists:
        try:
            collection = get_collection()
            chunk_count = collection.count()
        except Exception as e:
            chunk_count = 0
            st.error(f"Index error: {e}")

        st.markdown(
            f'<div class="chip-mono" style="color:#E7ECF5;font-size:0.8rem;margin-bottom:8px;">'
            f'📄 {html.escape(config.DOCX_PATH.name)}</div>',
            unsafe_allow_html=True,
        )
        if chunk_count > 0:
            st.markdown(_chip(f"Indexed · {chunk_count} chunks", "success"), unsafe_allow_html=True)
        else:
            st.markdown(_chip("Not indexed yet", "warn"), unsafe_allow_html=True)
            st.write("")
            if st.button("Build index now"):
                with st.spinner("Chunking, embedding, and indexing..."):
                    build_index(rebuild=False)
                st.rerun()

        st.write("")
        if st.button("🔁 Rebuild index"):
            with st.spinner("Re-embedding all chunks and extracting images..."):
                build_index(rebuild=True)
            st.rerun()
        st.caption("Rebuild after adding or changing images in the source document.")
    else:
        st.warning(
            f"Document not found at `{config.DOCX_PATH}`.\n\n"
            "Place your college_website.docx in the `data/` folder."
        )
        chunk_count = 0

    st.divider()
    st.markdown('<div class="side-label">Retrieval settings</div>', unsafe_allow_html=True)
    st.markdown(
        _chip(f"Chunk size {config.CHUNK_SIZE}", "neutral")
        + " "
        + _chip(f"Overlap {config.CHUNK_OVERLAP}", "neutral"),
        unsafe_allow_html=True,
    )
    st.write("")
    top_k = st.slider("Top-k chunks", min_value=1, max_value=10, value=config.TOP_K)

    section_options = ["All sections"] + (list_sections() if chunk_count else config.KNOWN_SECTIONS)
    section_filter = st.selectbox("Section filter", section_options)

    st.divider()
    st.markdown('<div class="side-label">Models · via OpenRouter</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div style="margin-bottom:6px;">{_chip("Generation", "neutral")} '
        f'<span class="chip-mono" style="color:#E7ECF5;">{html.escape(config.GENERATION_MODEL)}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div>{_chip("Embeddings", "neutral")} '
        f'<span class="chip-mono" style="color:#E7ECF5;">{html.escape(config.EMBEDDING_MODEL)}</span></div>',
        unsafe_allow_html=True,
    )

    st.divider()
    if st.button("🗑️ Clear conversation"):
        st.session_state.messages = []
        st.rerun()

# --- Main chat area ------------------------------------------------------
st.markdown(
    """
    <div class="hero">
        <div class="hero-icon">🎓</div>
        <div>
            <p class="hero-title">Ask about BVRIT</p>
            <p class="hero-sub">Answers are grounded strictly in the official college document, with page-level citations.</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

status_chips = [_chip(f"{top_k} chunks retrieved / query", "neutral")]
status_chips.append(_chip(section_filter, "neutral"))
if doc_exists and chunk_count:
    status_chips.insert(0, _chip("Knowledge base online", "success"))
else:
    status_chips.insert(0, _chip("Knowledge base offline", "danger"))
st.markdown(f'<div class="status-row">{"".join(status_chips)}</div>', unsafe_allow_html=True)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            if msg.get("refused"):
                st.markdown(_verdict_badge(True), unsafe_allow_html=True)
            if msg.get("citations"):
                with st.expander(f"📎 Sources ({len(msg['citations'])})"):
                    for c in msg["citations"]:
                        st.markdown(_citation_card(c["section"], c["page"], c["text"]), unsafe_allow_html=True)
            if msg.get("images"):
                _render_images(msg["images"])
            if msg.get("latency") is not None:
                st.markdown(f'<span class="latency-tag">⏱ {msg["latency"]:.2f}s</span>', unsafe_allow_html=True)

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
            if result.refused:
                st.markdown(_verdict_badge(True), unsafe_allow_html=True)
            st.markdown(result.answer)
            citations = [
                {"section": c.section, "page": c.page, "text": c.text} for c in result.chunks
            ]
            if citations:
                with st.expander(f"📎 Sources ({len(citations)})"):
                    for c in citations:
                        st.markdown(_citation_card(c["section"], c["page"], c["text"]), unsafe_allow_html=True)
            if result.images:
                _render_images(result.images)
            st.markdown(f'<span class="latency-tag">⏱ {result.latency_seconds:.2f}s</span>', unsafe_allow_html=True)

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

st.markdown(
    f'<div class="footer-note">Answers are generated by AI and grounded in the referenced college '
    f"document. For decisions that require official confirmation, contact "
    f"{html.escape(config.FALLBACK_CONTACT)}.</div>",
    unsafe_allow_html=True,
)