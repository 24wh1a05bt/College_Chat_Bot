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
from src.tools import get_tool_schemas, execute_tool_call
from src.memory import get_session_manager, reset_session

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

BEST EFFORT RULE
Before resorting to the refusal message, check if the context contains
*relevant* information that can be used to construct a reasonable answer.
If it does, use that information to answer the question even if the exact
phrasing or answer format is not present verbatim in the context. Only use
the refusal when absolutely no relevant information exists in the context
at all.

COMPLETENESS RULE
When the question asks you to list items (e.g. undergraduate branches,
companies, departments, eligibility criteria, etc.), enumerate ALL of them
explicitly from the context. Do not summarize by saying "five branches" or
"several companies" without naming them. The user needs to see the
complete list.

NO-HALLUCINATION RULE
This is critical: NEVER invent or make up any information that is not directly
present in the context. If a detail (like specific branch names, company names,
or numbers) does not appear in the context, do not guess it. Instead, state
what the context does say and note that the full details are not available.

For example, if the context says "BVRIT offers five B.Tech. branches" but does
NOT list their names, say "BVRIT offers five B.Tech. branches (listed in the
college's official materials)" — do NOT make up branch names.

FAITHFULNESS RULE
Do not add any interpretation, elaboration, or connective commentary that
isn't directly stated in the context, even if it seems like reasonable
inference. Every sentence in your answer must be traceable to a specific
chunk in the context. If you want to add context (e.g. "this is a strong
placement record"), only do so if the context itself characterizes it that
way — otherwise omit the editorializing and state only the fact.

CONFIDENCE RULE
When the context clearly states a fact (e.g. "CSE intake is 360"), state it
directly as a fact. Do NOT add qualifiers like "should be verified" or "it is
advised to check" for information that is explicitly stated in the context.
Only use such qualifiers for information that comes from third-party sources
or is explicitly noted as approximate.

CITATION FORMAT
Every factual claim must be followed by a citation in the exact format:
[Section Name, Page N]
Use the "section" and "page" values attached to each context chunk below.
If a single sentence draws on multiple chunks, cite all of them, e.g.
[Admissions, Page 2][Fee Structure, Page 3].

REFUSAL INSTRUCTION
If the answer is not contained in the context and the BEST EFFORT RULE above
does not apply, reply with:
"I don't have that information in the BVRIT knowledge base I was given.
For an accurate answer, please contact {fallback_contact}."
Do not apologize excessively or speculate further after the refusal.

CONFLICT HANDLING
If two chunks in the context give different information on the same fact,
present both values, cite each separately, and explicitly note the
discrepancy (e.g. "Two sections of the source document give different
figures here: ... This should be checked with the college.").

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
Be concise and factual. Answer directly with the information from the
context. Do not make promises about individual outcomes (admission chances,
placement guarantees, scholarship eligibility). Do not give medical, legal,
or financial advice.
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

# Section-title keywords for the hybrid keyword-boost fallback. These are
# short, high-signal sections (Mission, Vision, Accreditation, NIRF) that
# pure vector search sometimes ranks below more generic chunks that mention
# the same words only in passing (e.g. an "About" chunk that happens to
# contain the word "mission" once).
_KEYWORD_SECTION_TERMS = [
    "mission", "vision", "accredit", "nirf", "rank",
    "naac", "nba", "aicte", "ugc",
]


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


def _parse_images(raw_images: str) -> list[dict]:
    """Normalize whatever shape ended up in Chroma metadata (a stale/rebuilt
    index could have a single dict, a bare filename string, or a proper
    list of dicts) into a consistent list[dict]."""
    images: list[dict] = []
    if not raw_images:
        return images
    try:
        parsed = json.loads(raw_images)
    except json.JSONDecodeError:
        parsed = []
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
    return images


def _keyword_matched_chunks(query: str, exclude_texts: set[str]) -> list[RetrievedChunk]:
    """Fall back to a metadata/text keyword scan for short, high-signal
    sections (Mission, Vision, Accreditation, NIRF) that pure vector search
    sometimes ranks below more generic chunks mentioning the same words in
    passing. Only triggers when the query itself contains one of these
    keywords, and is cheap because it only runs a `.get()` over the already
    in-memory collection metadata (no extra embedding calls)."""
    ql = query.lower()
    matched_terms = [kw for kw in _KEYWORD_SECTION_TERMS if kw in ql]
    if not matched_terms:
        return []

    collection = get_collection()
    got = collection.get(include=["documents", "metadatas"])
    extra: list[RetrievedChunk] = []
    for doc, meta in zip(got["documents"], got["metadatas"]):
        if doc in exclude_texts:
            continue
        section = (meta.get("section") or "").lower()
        if any(term in section for term in matched_terms):
            extra.append(
                RetrievedChunk(
                    text=doc,
                    section=meta.get("section", "Unknown"),
                    page=meta.get("page", 0),
                    source=meta.get("source", ""),
                    distance=0.0,  # treat as highest relevance - guaranteed match
                    images=_parse_images(meta.get("images", "") or ""),
                )
            )
    return extra


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
        chunks.append(
            RetrievedChunk(
                text=doc,
                section=meta.get("section", "Unknown"),
                page=meta.get("page", 0),
                source=meta.get("source", ""),
                distance=dist,
                images=_parse_images(meta.get("images", "") or ""),
            )
        )

    # Hybrid boost: guarantee section-title keyword matches are included,
    # since short high-signal sections (Mission/Vision/Accreditation/NIRF)
    # can otherwise lose out to longer, more generic chunks in pure vector
    # search. Skipped when a section_filter is already active since the
    # filter already scopes retrieval to a specific section.
    if not section_filter or section_filter == "All sections":
        seen_texts = {c.text for c in chunks}
        boosted = _keyword_matched_chunks(query, seen_texts)
        if boosted:
            chunks = boosted + chunks  # keyword-exact sections take priority

    return chunks


def _format_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for c in chunks:
        blocks.append(f"[{c.section}, Page {c.page}]\n{c.text}")
    return "\n\n---\n\n".join(blocks)


# --- Input validation helpers ------------------------------------------------

def _is_gibberish(query: str) -> bool:
    """Detect nonsensical / garbage input (random keyboard mash, emoji-only)."""
    stripped = query.strip()
    if not stripped:
        return True
    # If query is very short and contains no real words (emoji-only, symbols only)
    if len(stripped) < 3:
        return True
    # Compute ratio of letter characters to total length
    letters = sum(c.isalpha() for c in stripped)
    non_alpha_ratio = 1.0 - (letters / max(len(stripped), 1))
    # If more than 70% of characters are non-alphabetic (emoji, numbers, punctuation)
    if non_alpha_ratio > 0.70:
        return True
    # If the query doesn't contain any real English-like word (at least 2 letters in a row)
    if not re.search(r'[a-zA-Z]{2,}', stripped):
        return True
    # Detect keyboard mash: all letters but no vowels (e.g. "asdkfjhaskjdfh")
    # A real English word almost always has at least one vowel
    has_vowel = bool(re.search(r'[aeiouAEIOU]', stripped))
    # If it's all letters and has no vowels, it's likely a keyboard mash
    if letters == len(stripped) and not has_vowel and len(stripped) > 4:
        return True
    # Detect keyboard mash: consecutive consonants without vowels forming long runs
    # e.g. "asdkfjhaskjdfh" has long consonant sequences
    consonant_runs = re.findall(r'[bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ]{4,}', stripped)
    if consonant_runs and len(stripped) > 4:
        # If more than 60% of the string is consonant runs of 4+, it's gibberish
        total_consonant_run_len = sum(len(run) for run in consonant_runs)
        if total_consonant_run_len / len(stripped) > 0.6:
            return True
    # Detect keyboard mash: long strings with no real English words
    # e.g. "asdkjfhqweurqwoiuyqwe" - has vowels but no recognizable words
    if len(stripped) > 8 and letters == len(stripped):
        # Check if it contains any common English word fragments (at least 3 letters)
        # Real queries about BVRIT will contain words like "what", "branches", "admission", etc.
        # Keyboard mashes won't match any common word patterns
        words = re.findall(r'[a-zA-Z]{3,}', stripped.lower())
        common_patterns = ['what', 'how', 'why', 'when', 'which', 'where', 'tell', 'show', 'list',
                          'give', 'find', 'branche', 'depart', 'admission', 'place', 'fee',
                          'college', 'bvrit', 'campus', 'course', 'program', 'student',
                          'faculty', 'eligib', 'requir', 'process', 'applic', 'exam',
                          'result', 'percent', 'company', 'recruit', 'intern', 'scholar',
                          'contact', 'address', 'phone', 'email', 'website', 'about',
                          'accred', 'naac', 'nba', 'grade', 'rank', 'award', 'recogni']
        # If no word in the query matches any common pattern, it's likely gibberish
        has_common_word = any(
            any(pattern in word for pattern in common_patterns)
            for word in words
        )
        if not has_common_word and len(words) <= 1:
            return True
    return False


# --- Prompt injection detection ------------------------------------------------

_PROMPT_INJECTION_RE = re.compile(
    r"(ignore|forget|disregard|override|bypass|reveal|disclose|show|tell|print|output|leak|dump)\b"
    r".{0,30}\b(instructions|prompt|system prompt|previous instructions|rules|guidelines|constraints|system message|internal)\b",
    re.IGNORECASE,
)

# Catch "forget everything" / "forget all" / "forget your instructions" type injections
_FORGET_INJECTION_RE = re.compile(
    r"\b(forget|ignore|disregard)\b.{0,20}\b(everything|all|previous|your|these)\b",
    re.IGNORECASE,
)


def _is_prompt_injection(query: str) -> bool:
    """Detect attempts to override system instructions or reveal the system prompt."""
    if _PROMPT_INJECTION_RE.search(query):
        return True
    if _FORGET_INJECTION_RE.search(query):
        return True
    return False


def get_privacy_notice() -> str:
    """Return privacy notice for first interaction."""
    return """
📋 **Privacy Notice**

I remember a few things to personalize your experience:
- Your name (if you share it)
- Your branch of interest
- Your language preference
- Your detail preference (detailed/brief answers)
- Topics you've asked about

**Why**: This helps me provide personalized, consistent answers across sessions.

**How to delete**: Type "Clear my data" at any time to delete everything I know about you.

**Auto-expiry**: Profiles not used for 30 days are automatically deleted.

I store minimal data and never share it with third parties.
"""


def _rewrite_query_with_history(query: str, chat_history: list[dict] | None, memory_history: list[dict] | None = None) -> str:
    """Rewrite the user's query as a standalone question using conversation history.
    This resolves references like 'the first one', 'that branch', etc.
    
    Uses either the provided chat_history or memory_history (from the session manager).
    """
    # Determine which history to use
    history = chat_history if chat_history else memory_history
    if not history or len(history) < 2:
        return query  # No history to reference
    
    # Check if query contains references that need history
    reference_patterns = [
        r'\b(first|second|third|last|next|previous|that|this|those|these|it|them)\b',
        r'\b(the one|that branch|that department|that topic)\b',
        r'\b(tell me more|elaborate|explain further|go deeper)\b',
        r'\b(what about|same as|similar to)\b',
        r'\b(my name|my branch|my interest|what did I)\b',
    ]
    needs_rewrite = any(re.search(p, query.lower()) for p in reference_patterns)
    
    if not needs_rewrite:
        return query
    
    # Build a compact history string
    history_text = "\n".join([
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:300]}"
        for m in history[-6:]  # last 3 turns
    ])
    
    rewrite_prompt = f"""Given the conversation history and the user's latest query (which may contain references like "the first one"), rewrite the query as a standalone question that doesn't need any context to understand.

Conversation history:
{history_text}

User's latest query: {query}

Rewritten standalone question:"""
    
    try:
        from src.llm_client import chat_completion
        rewritten, _ = chat_completion(
            messages=[
                {"role": "system", "content": "You are a query rewriter. Rewrite user queries with references into standalone questions. Respond with ONLY the rewritten question, nothing else."},
                {"role": "user", "content": rewrite_prompt}
            ],
            model=config.GENERATION_MODEL,
            temperature=0.1,
            max_tokens=200
        )
        rewritten = rewritten.strip().strip('"').strip("'")
        if rewritten:
            return rewritten
    except Exception:
        pass
    
    return query


def answer(
    query: str,
    chat_history: list[dict] | None = None,
    top_k: int = None,
    section_filter: str | None = None,
    session_id: str = None,
    user_id: str = None,
    use_summarization: bool = True,
) -> RAGResponse:
    start = time.time()
    
    # Get session manager
    session_mgr = get_session_manager(session_id, user_id)
    memory = session_mgr.memory
    
    # Check for special commands
    if query.strip().lower() == "clear my data":
        session_mgr.clear_user_data()
        latency = time.time() - start
        return RAGResponse(
            answer="✅ Your data has been cleared. I no longer remember any personal information about you.",
            chunks=[],
            latency_seconds=latency,
            refused=False,
        )
    
    # Check for privacy command
    if query.strip().lower() in ["privacy policy", "privacy notice", "what do you remember"]:
        latency = time.time() - start
        policy = get_privacy_notice()
        return RAGResponse(
            answer=policy,
            chunks=[],
            latency_seconds=latency,
            refused=False,
        )
    
    # --- Input validation (pre-retrieval) ------------------------------------
    if not query or not query.strip():
        latency = time.time() - start
        return RAGResponse(
            answer="I'm sorry, but I need a specific question to assist you. Please type a question about BVRIT (e.g. admissions, fees, placements).",
            chunks=[],
            latency_seconds=latency,
            refused=False,
        )

    if _is_gibberish(query):
        latency = time.time() - start
        return RAGResponse(
            answer="I'm sorry, but I didn't understand that. Could you please rephrase your question?",
            chunks=[],
            latency_seconds=latency,
            refused=False,
        )

    if _is_prompt_injection(query):
        latency = time.time() - start
        return RAGResponse(
            answer="I'm sorry, but I cannot disclose my internal instructions or system prompts. I'm here to help you with questions about BVRIT Hyderabad.",
            chunks=[],
            latency_seconds=latency,
            refused=False,
        )

    # Get memory history for coreference resolution (when chat_history not provided)
    memory_history = memory.get_history(max_turns=10) if use_summarization else memory.get_history()
    
    # Rewrite query with conversation history for coreference resolution
    retrieval_query = _rewrite_query_with_history(query, chat_history, memory_history)
    chunks = retrieve(retrieval_query, top_k=top_k, section_filter=section_filter)

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
    
    # Build system prompt with personalization
    system_prompt = SYSTEM_PROMPT
    
    # Add user profile context
    profile_context = session_mgr.get_system_prompt_injection()
    if profile_context:
        system_prompt += f"\n\nUSER CONTEXT:\n{profile_context}"
    
    # Build messages with conversation history
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add conversation summary if available
    if memory.get_summary():
        messages.append({
            "role": "system",
            "content": f"Previous conversation summary: {memory.get_summary()}"
        })
    
    # Add recent conversation history
    if chat_history:
        # Use provided chat_history if given (for Streamlit)
        messages.extend(chat_history[-6:])  # keep last 3 turns for context
    else:
        # Use memory-based history
        history = memory.get_history(max_turns=10) if use_summarization else memory.get_history()
        if history:
            messages.extend(history)
    
    # Add current query with context
    messages.append({
        "role": "user",
        "content": f"CONTEXT:\n{context}\n\nQUESTION: {query}",
    })
    
    # Store user message in memory
    memory.add_message("user", query)

    # --- Tool-using LLM call (max 2 rounds of tool calls) --------------------
    # Only provide tools on the first round. If the model calls a tool, we
    # execute it and feed the result back for a second round without tools.
    tool_schemas = get_tool_schemas()
    text = ""
    for round_idx in range(2):
        result, tool_calls = chat_completion(
            messages,
            model=config.GENERATION_MODEL,
            temperature=0.1,
            max_tokens=700,
            tools=tool_schemas if round_idx == 0 else None,
        )
        if tool_calls and round_idx == 0:
            # Build the assistant message that includes tool_calls metadata
            # The OpenAI API requires the assistant message to have a
            # "tool_calls" array so the subsequent "tool" role messages
            # can reference the call IDs.
            assistant_msg = {
                "role": "assistant",
                "content": result if result else None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                        },
                    }
                    for tc in tool_calls
                ],
            }
            messages.append(assistant_msg)
            for tc in tool_calls:
                tool_result = execute_tool_call(tc)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })
            # Continue to next round (without tools) to get the final answer
        else:
            text = result
            break

    latency = time.time() - start
    
    # Store assistant response in memory
    memory.add_message("assistant", text)

    # Update profile if we learned new information
    _update_profile_from_conversation(session_mgr, query, text)

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


def _update_profile_from_conversation(session_mgr, query: str, response: str):
    """Extract user information from conversation and update profile."""
    profile = session_mgr.profile
    
    # Extract name
    if not profile.name:
        name_match = re.search(r"my name is (\w+)", query, re.IGNORECASE)
        if name_match:
            profile.name = name_match.group(1)
            session_mgr.update_profile()
    
    # Extract branch interest
    if not profile.branch_interest:
        branches = ["CSE", "Mechanical", "Civil", "Electronics", "ECE", "EEE", "IT"]
        for branch in branches:
            if branch.lower() in query.lower() and "interested" in query.lower():
                profile.branch_interest = branch
                session_mgr.update_profile()
                break
    
    # Extract detail level preference
    if "brief" in query.lower() or "concise" in query.lower():
        profile.detail_level = "brief"
        session_mgr.update_profile()
    elif "detailed" in query.lower() or "comprehensive" in query.lower():
        profile.detail_level = "detailed"
        session_mgr.update_profile()
    
    # Track topics
    topics = ["admission", "fee", "placement", "hostel", "faculty", "scholarship", "campus"]
    for topic in topics:
        if topic in query.lower() and topic not in profile.prior_topics:
            profile.prior_topics.append(topic)
            session_mgr.update_profile()