"""
College FAQ Chatbot - Streamlit chat UI.

Run with:
    streamlit run app.py
"""
import html
import os
import hashlib
import time
import datetime as dt

import streamlit as st

from src import config
from src.ingest import build_index, get_collection, list_sections
from src.rag_chain import answer, get_privacy_notice
from src.memory import reset_session

st.set_page_config(
    page_title="BVRIT AI Assistant",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Session state ---------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []  # [{role, content, citations, refused, latency, timestamp, feedback}]

if "first_interaction" not in st.session_state:
    st.session_state.first_interaction = True

if "user_id" not in st.session_state:
    st.session_state.user_id = f"user_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}"

if "session_id" not in st.session_state:
    st.session_state.session_id = f"session_{time.strftime('%Y%m%d_%H%M%S')}"

if "pending_query" not in st.session_state:
    st.session_state.pending_query = None


# --- Content ------------------------------------------------------------
TOPIC_CARDS = [
    ("🎓", "Admissions", "Eligibility, cutoffs, documents", "What are the admission requirements, eligibility criteria and cutoffs?"),
    ("💰", "Fee Structure", "Tuition, hostel, scholarships", "What is the fee structure for B.Tech programs?"),
    ("📈", "Placements", "Recruiters, packages, stats", "What are the latest placement statistics and top recruiters?"),
    ("🏠", "Hostel", "Rooms, mess, facilities", "What hostel facilities are available and what do they cost?"),
    ("🎁", "Scholarships", "Merit & need-based aid", "What scholarships are available and how do I apply for them?"),
    ("🏫", "Campus Life", "Clubs, events, facilities", "What is campus life like — clubs, events and facilities?"),
]

BOT_AVATAR = "🤖"
USER_AVATAR = "🙂"


def _greeting() -> str:
    hour = dt.datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


# --- Design system ----------------------------------------------------------
# A dark, modern "AI product" look: deep slate background, blue/indigo
# gradient branding, floating glass input, chat-bubble message rows.
# Everything below is plain HTML/CSS rendered through st.markdown, so it
# can't be knocked out of alignment by Streamlit's internal class names
# changing between versions.
def _inject_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');

        :root{
            --bg:#0F172A;
            --bg-sidebar:#111827;
            --surface:#1E293B;
            --surface-2:#243144;
            --user-bubble:#2563EB;
            --text:#F8FAFC;
            --text-muted:#94A3B8;
            --border:rgba(255,255,255,0.08);
            --accent:#3B82F6;
            --accent-2:#4F46E5;
            --gradient:linear-gradient(135deg,#2563EB 0%,#4F46E5 100%);
            --success:#22C55E;
            --success-bg:rgba(34,197,94,0.12);
            --warn:#F59E0B;
            --warn-bg:rgba(245,158,11,0.12);
            --danger:#EF4444;
            --danger-bg:rgba(239,68,68,0.12);
        }

        .stApp{ background:var(--bg); }
        html, body, [class*="css"]{ font-family:'Inter',sans-serif; color:var(--text); }
        h1,h2,h3{ font-family:'Plus Jakarta Sans',sans-serif; }

        /* Center + cap width for a comfortable reading column on wide monitors */
        .main .block-container{
            max-width:900px; margin:0 auto; padding-top:1.6rem; padding-bottom:6rem;
        }

        /* ---- Sidebar ---- */
        section[data-testid="stSidebar"]{
            background:var(--bg-sidebar);
            border-right:1px solid var(--border);
        }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] .stMarkdown,
        section[data-testid="stSidebar"] .stCaption{
            color:var(--text) !important;
        }
        section[data-testid="stSidebar"] hr{ border-color:var(--border); }
        section[data-testid="stSidebar"] .stButton>button{
            background:var(--gradient);
            color:#fff;
            border:none;
            border-radius:10px;
            font-weight:600;
            width:100%;
            transition:transform .15s ease, box-shadow .15s ease;
        }
        section[data-testid="stSidebar"] .stButton>button:hover{
            transform:translateY(-1px);
            box-shadow:0 6px 16px rgba(37,99,235,0.35);
        }

        /* ---- Sidebar brand block ---- */
        .brand-block{ padding:4px 0 18px 0; border-bottom:1px solid var(--border); margin-bottom:16px; }
        .brand-crest{
            display:inline-flex; align-items:center; justify-content:center;
            width:40px; height:40px; border-radius:11px;
            background:var(--gradient); color:#fff;
            font-weight:800; font-size:1.1rem; margin-bottom:10px;
        }
        .brand-name{ font-family:'Plus Jakarta Sans',sans-serif; font-size:1.1rem; font-weight:700; color:#FFFFFF; line-height:1.25; }
        .brand-tagline{ font-size:0.76rem; color:var(--text-muted); letter-spacing:.02em; text-transform:uppercase; }

        .side-label{
            font-size:0.72rem; font-weight:600; letter-spacing:.06em; text-transform:uppercase;
            color:var(--text-muted) !important; margin:2px 0 8px 0;
        }
        .side-recent-item{
            font-size:0.82rem; color:var(--text-muted); padding:6px 0; border-bottom:1px solid var(--border);
            overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
        }

        /* ---- Chips / badges ---- */
        .chip{
            display:inline-flex; align-items:center; gap:6px;
            padding:4px 10px; border-radius:999px; font-size:0.78rem; font-weight:600;
            border:1px solid transparent; white-space:nowrap;
        }
        .chip-dot{ width:7px; height:7px; border-radius:50%; display:inline-block; }
        .chip-success{ background:var(--success-bg); color:var(--success); border-color:rgba(34,197,94,0.25); }
        .chip-success .chip-dot{ background:var(--success); }
        .chip-warn{ background:var(--warn-bg); color:var(--warn); border-color:rgba(245,158,11,0.25); }
        .chip-warn .chip-dot{ background:var(--warn); }
        .chip-danger{ background:var(--danger-bg); color:var(--danger); border-color:rgba(239,68,68,0.25); }
        .chip-danger .chip-dot{ background:var(--danger); }
        .chip-neutral{ background:var(--surface); color:var(--text-muted); border-color:var(--border); }
        .chip-mono{ font-family:'IBM Plex Mono',monospace; font-weight:500; font-size:0.74rem; }

        /* ---- Simple gradient header (no bordered hero card) ---- */
        .topbar{ display:flex; align-items:center; gap:14px; margin-bottom:6px; }
        .topbar-mark{
            width:44px; height:44px; border-radius:12px; flex-shrink:0;
            background:var(--gradient); display:flex; align-items:center; justify-content:center;
            font-weight:800; color:#fff; font-size:1.15rem;
            box-shadow:0 6px 18px rgba(37,99,235,0.35);
        }
        .topbar-title{ font-family:'Plus Jakarta Sans',sans-serif; font-weight:800; font-size:1.35rem; color:#fff; margin:0; }
        .topbar-sub{ color:var(--text-muted); font-size:0.86rem; margin-top:1px; }
        .topbar-meta{ font-size:0.76rem; color:var(--text-muted); margin-top:2px; }
        .topbar-meta b{ color:#CBD5E1; font-weight:600; }

        .online-dot{
            display:inline-flex; align-items:center; gap:5px;
            font-size:0.76rem; font-weight:600; color:var(--success);
        }
        .online-dot .pulse{
            width:8px; height:8px; border-radius:50%; background:var(--success);
            animation:pulse 2s infinite;
        }
        @keyframes pulse{
            0%{ box-shadow:0 0 0 0 rgba(34,197,94,0.5); }
            70%{ box-shadow:0 0 0 7px rgba(34,197,94,0); }
            100%{ box-shadow:0 0 0 0 rgba(34,197,94,0); }
        }

        .status-row{ display:flex; flex-wrap:wrap; gap:8px; margin:14px 0 20px 0; }

        /* ---- Chat bubbles ---- */
        div[data-testid="stChatMessage"]{
            border:none;
            border-radius:24px;
            padding:18px;
            margin-bottom:6px;
            max-width:70%;
            box-shadow:0 2px 8px rgba(0,0,0,0.18);
            animation: bubble-in .18s ease-out;
            transition:transform .15s ease;
        }
        @keyframes bubble-in{
            from{ opacity:0; transform:translateY(4px); }
            to{ opacity:1; transform:translateY(0); }
        }

        div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]){
            background:var(--surface);
            border:1px solid var(--border);
            margin-right:auto;
            border-bottom-left-radius:6px;
        }

        div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]){
            background:linear-gradient(135deg,var(--user-bubble) 0%,var(--accent-2) 100%);
            margin-left:auto;
            flex-direction:row-reverse;
            border-bottom-right-radius:6px;
        }
        div[data-testid="stChatMessage"] p,
        div[data-testid="stChatMessage"] li,
        div[data-testid="stChatMessage"] span,
        div[data-testid="stChatMessage"] .stMarkdown{
            color:var(--text) !important;
        }
        div[data-testid="stChatMessage"] code{
            background:rgba(255,255,255,0.08); color:#E2E8F0;
        }

        .msg-timestamp{
            font-size:0.7rem; color:var(--text-muted); margin:2px 4px 14px 4px;
        }
        .msg-timestamp.right{ text-align:right; }
        .msg-timestamp.left{ text-align:left; }

        /* ---- Quick actions row under assistant messages ---- */
        [class*="st-key-qa_row_"] .stButton>button{
            background:transparent; border:1px solid var(--border); color:var(--text-muted);
            border-radius:8px; padding:2px 10px; font-size:0.82rem; min-height:0; height:30px;
            transition:all .15s ease;
        }
        .qa-row .stButton>button:hover{ border-color:var(--accent); color:#fff; background:rgba(59,130,246,0.12); }

        /* ---- Typing / loading theatre ---- */
        .loading-stage{
            display:flex; align-items:center; gap:10px; color:var(--text-muted); font-size:0.9rem; padding:4px 0;
        }
        .typing-dots{ display:inline-flex; gap:4px; }
        .typing-dots span{
            width:6px; height:6px; border-radius:50%; background:var(--accent);
            animation:typing-bounce 1.1s infinite ease-in-out;
        }
        .typing-dots span:nth-child(2){ animation-delay:.15s; }
        .typing-dots span:nth-child(3){ animation-delay:.3s; }
        @keyframes typing-bounce{
            0%, 60%, 100%{ transform:translateY(0); opacity:.5; }
            30%{ transform:translateY(-4px); opacity:1; }
        }

        /* ---- Verdict badges ---- */
        .verdict-badge{
            display:inline-flex; align-items:center; gap:6px;
            padding:3px 11px; border-radius:999px; font-size:0.74rem; font-weight:700;
            letter-spacing:.02em; text-transform:uppercase; margin-bottom:8px;
        }
        .verdict-refused{ background:var(--warn-bg); color:var(--warn); border:1px solid rgba(245,158,11,0.25); }
        .verdict-grounded{ background:var(--success-bg); color:var(--success); border:1px solid rgba(34,197,94,0.25); }

        /* ---- Citation cards ---- */
        .citation-card{
            border:1px solid var(--border); border-left:3px solid var(--accent);
            border-radius:10px; padding:10px 12px; margin-bottom:8px; background:var(--surface-2);
        }
        .citation-tag{
            display:inline-block; font-family:'IBM Plex Mono',monospace; font-size:0.72rem;
            font-weight:600; color:#0F172A; background:#93C5FD;
            border-radius:5px; padding:2px 7px; margin-bottom:6px;
        }
        .citation-text{ font-size:0.86rem; color:#E2E8F0; font-style:italic; line-height:1.45; }

        .latency-tag{
            font-family:'IBM Plex Mono',monospace; font-size:0.76rem; color:var(--text-muted);
        }

        .footer-note{
            margin-top:28px; padding-top:14px; border-top:1px solid var(--border);
            color:var(--text-muted); font-size:0.8rem; text-align:center;
        }

        /* Memory status indicator */
        .memory-indicator {
            display:inline-flex; align-items:center; gap:6px;
            padding:4px 12px; border-radius:999px; font-size:0.72rem;
            background:rgba(255,255,255,0.06); color:var(--text-muted);
            border:1px solid var(--border);
        }
        .memory-indicator .dot {
            width:6px; height:6px; border-radius:50%; display:inline-block;
        }
        .dot-active { background:var(--success); }
        .dot-inactive { background:#9e9e9e; }

        /* ---- Floating glass chat input ---- */
        div[data-testid="stChatInput"]{
            border-radius:28px !important;
            background:rgba(30,41,59,0.85) !important;
            backdrop-filter:blur(12px);
            -webkit-backdrop-filter:blur(12px);
            box-shadow:0 15px 40px rgba(0,0,0,0.35);
            border:1px solid var(--border) !important;
        }
        div[data-testid="stChatInput"] textarea{
            border-radius:28px !important;
            color:var(--text) !important;
        }

        /* ---- Empty-state welcome screen ---- */
        .empty-state{ text-align:center; padding:38px 20px 6px 20px; }
        .empty-title{
            font-family:'Plus Jakarta Sans',sans-serif; font-weight:800; font-size:1.7rem;
            background:var(--gradient); -webkit-background-clip:text; background-clip:text; color:transparent;
            margin-bottom:6px;
        }
        .empty-sub{ color:var(--text-muted); font-size:0.96rem; }

        .suggestions-label{
            font-size:0.76rem; font-weight:600; letter-spacing:.04em; text-transform:uppercase;
            color:var(--text-muted); text-align:center; margin:24px 0 10px 0;
        }

        /* Topic cards (scoped via st.container(key=...)) */
        .st-key-topic_grid .stButton>button{
            background:var(--surface);
            border:1px solid var(--border);
            color:var(--text);
            border-radius:16px;
            padding:16px 16px;
            font-weight:600;
            font-size:0.92rem;
            text-align:left;
            white-space:pre-line;
            height:100%;
            min-height:88px;
            box-shadow:0 1px 3px rgba(0,0,0,0.16);
            transition:all .2s ease;
        }
        .st-key-topic_grid .stButton>button:hover{
            border-color:var(--accent);
            background:var(--surface-2);
            transform:translateY(-3px);
            box-shadow:0 10px 24px rgba(37,99,235,0.22);
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
        f'<div class="citation-tag">📄 {html.escape(section)} · Page {page}</div>'
        f'<div class="citation-text">“{html.escape(snippet)}”</div>'
        "</div>"
    )


def _timestamp() -> str:
    return time.strftime("%I:%M %p").lstrip("0")


def _render_timestamp(ts: str, role: str) -> None:
    side = "right" if role == "user" else "left"
    st.markdown(f'<div class="msg-timestamp {side}">{html.escape(ts)}</div>', unsafe_allow_html=True)


def _run_answer(query: str, top_k: int, section_filter: str):
    """Runs the RAG pipeline with a short staged-progress display, then
    reveals the answer with a simulated word-by-word stream."""
    stage_ph = st.empty()
    stages = [
        "🔍 Searching knowledge base",
        "📚 Retrieving relevant documents",
        "🧠 Generating answer",
    ]
    for s in stages:
        stage_ph.markdown(
            f'<div class="loading-stage">{s}'
            f'<span class="typing-dots"><span></span><span></span><span></span></span></div>',
            unsafe_allow_html=True,
        )
        time.sleep(0.35)

    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages[:-1]
    ]
    result = answer(
        query,
        chat_history=history,
        top_k=top_k,
        section_filter=section_filter,
        user_id=st.session_state.user_id,
        session_id=st.session_state.session_id,
        use_summarization=True,
    )
    stage_ph.empty()

    # Simulated streaming reveal (backend returns the full answer at once;
    # this just paces how it appears so it *feels* like live generation).
    answer_ph = st.empty()
    words = result.answer.split(" ")
    per_word_delay = min(0.03, 1.4 / max(len(words), 1))
    partial = ""
    for i, w in enumerate(words):
        partial += w + " "
        if i % 3 == 0 or i == len(words) - 1:
            answer_ph.markdown(partial + "▌")
            time.sleep(per_word_delay * 3)
    answer_ph.markdown(result.answer)

    return result


_inject_css()

# --- Sidebar -----------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div class="brand-block">
            <div class="brand-crest">B</div>
            <div class="brand-name">BVRIT AI</div>
            <div class="brand-tagline">Campus Assistant</div>
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
            f'<div class="chip-mono" style="color:#E2E8F0;font-size:0.8rem;margin-bottom:8px;">'
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
        f'<span class="chip-mono" style="color:#E2E8F0;">{html.escape(config.GENERATION_MODEL)}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div>{_chip("Embeddings", "neutral")} '
        f'<span class="chip-mono" style="color:#E2E8F0;">{html.escape(config.EMBEDDING_MODEL)}</span></div>',
        unsafe_allow_html=True,
    )

    st.divider()
    st.markdown('<div class="side-label">Memory</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="memory-indicator"><span class="dot dot-active"></span> Session memory active</div>',
        unsafe_allow_html=True,
    )
    st.caption(f"Summarizes every {config.MEMORY_SUMMARIZE_AFTER} turns")
    st.caption(f"Profiles auto-expire after {config.MEMORY_AUTO_EXPIRE_DAYS} days")

    # Lightweight "recent questions" recap for this session. Full
    # multi-day chat history (Today / Yesterday, switchable threads)
    # would need a persistence layer this app doesn't have yet.
    user_turns = [m for m in st.session_state.messages if m["role"] == "user"]
    if user_turns:
        st.divider()
        st.markdown('<div class="side-label">This session</div>', unsafe_allow_html=True)
        for m in user_turns[-6:][::-1]:
            preview = (m["content"][:38] + "…") if len(m["content"]) > 38 else m["content"]
            st.markdown(f'<div class="side-recent-item">💬 {html.escape(preview)}</div>', unsafe_allow_html=True)

    st.write("")
    if st.button("🗑️ Clear conversation"):
        st.session_state.messages = []
        reset_session()
        st.rerun()

    if st.button("🔒 Clear my data"):
        st.session_state.messages.append({"role": "user", "content": "clear my data", "timestamp": _timestamp()})
        st.rerun()

# --- Main chat area ------------------------------------------------------
st.markdown(
    """
    <div class="topbar">
        <div class="topbar-mark">B</div>
        <div>
            <p class="topbar-title">BVRIT AI Assistant</p>
            <p class="topbar-sub">Your intelligent campus assistant</p>
            <p class="topbar-meta"><b>Powered by RAG</b> &nbsp;•&nbsp; <b>Sources Verified</b> &nbsp;•&nbsp;
            <span class="online-dot"><span class="pulse"></span>Online now</span></p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

status_chips = [_chip(f"{top_k} chunks / query", "neutral")]
status_chips.append(_chip(section_filter, "neutral"))
if doc_exists and chunk_count:
    status_chips.insert(0, _chip("Knowledge base online", "success"))
else:
    status_chips.insert(0, _chip("Knowledge base offline", "danger"))
st.markdown(f'<div class="status-row">{"".join(status_chips)}</div>', unsafe_allow_html=True)

# Show privacy notice on first interaction
if st.session_state.first_interaction:
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        st.markdown(get_privacy_notice())
    st.session_state.first_interaction = False

# Welcome screen + topic cards, shown only before the first message
if not st.session_state.messages:
    st.markdown(
        f"""
        <div class="empty-state">
            <div class="empty-title">{_greeting()} 👋</div>
            <div class="empty-sub">How can I help today?</div>
        </div>
        <div class="suggestions-label">Popular topics</div>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="topic_grid"):
        row1 = st.columns(3)
        row2 = st.columns(3)
        for col, (icon, title, subtitle, question) in zip(row1 + row2, TOPIC_CARDS):
            with col:
                if st.button(f"{icon}  {title}\n{subtitle}", key=f"topic_{title}", use_container_width=True):
                    st.session_state.pending_query = question
                    st.rerun()

for idx, msg in enumerate(st.session_state.messages):
    avatar = USER_AVATAR if msg["role"] == "user" else BOT_AVATAR
    with st.chat_message(msg["role"], avatar=avatar):
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
    if msg.get("timestamp"):
        _render_timestamp(msg["timestamp"], msg["role"])

    # Quick actions under assistant replies: like / dislike / regenerate
    if msg["role"] == "assistant" and idx > 0:
        with st.container(key=f"qa_row_{idx}"):
            c1, c2, c3, _ = st.columns([1, 1, 1.4, 6])
            feedback = msg.get("feedback")
            with c1:
                if st.button("👍" if feedback != "up" else "✅👍", key=f"up_{idx}"):
                    msg["feedback"] = None if feedback == "up" else "up"
                    st.rerun()
            with c2:
                if st.button("👎" if feedback != "down" else "✅👎", key=f"down_{idx}"):
                    msg["feedback"] = None if feedback == "down" else "down"
                    st.rerun()
            with c3:
                if st.button("🔄 Regenerate", key=f"regen_{idx}"):
                    prev_user = st.session_state.messages[idx - 1]
                    if prev_user["role"] == "user":
                        with st.spinner(""):
                            result = _run_answer(prev_user["content"], top_k, section_filter)
                        msg["content"] = result.answer
                        msg["citations"] = [
                            {"section": c.section, "page": c.page, "text": c.text} for c in result.chunks
                        ]
                        msg["refused"] = result.refused
                        msg["latency"] = result.latency_seconds
                        msg["images"] = result.images
                        msg["timestamp"] = _timestamp()
                        st.rerun()

query = st.chat_input("Ask anything about BVRIT...")

if not query and st.session_state.get("pending_query"):
    query = st.session_state.pending_query
    st.session_state.pending_query = None

if query:
    if not config.DOCX_PATH.exists() or chunk_count == 0:
        st.error("The knowledge base isn't indexed yet. Use the sidebar to build the index first.")
    else:
        st.session_state.messages.append({"role": "user", "content": query, "timestamp": _timestamp()})
        with st.chat_message("user", avatar=USER_AVATAR):
            st.markdown(query)
        _render_timestamp(st.session_state.messages[-1]["timestamp"], "user")

        with st.chat_message("assistant", avatar=BOT_AVATAR):
            result = _run_answer(query, top_k, section_filter)
            if result.refused:
                st.markdown(_verdict_badge(True), unsafe_allow_html=True)
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
                "timestamp": _timestamp(),
                "feedback": None,
            }
        )
        st.rerun()

st.markdown(
    f'<div class="footer-note">Answers are generated by AI and grounded in the referenced college '
    f"document. For decisions that require official confirmation, contact "
    f"{html.escape(config.FALLBACK_CONTACT)}.</div>",
    unsafe_allow_html=True,
)