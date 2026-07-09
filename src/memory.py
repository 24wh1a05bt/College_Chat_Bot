# src/memory.py
"""
Memory management for the BVRIT chatbot.
Handles short-term, medium-term, and long-term memory.
"""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any
import hashlib

from src import config

# --- Short-term memory (conversation history) ---

class ConversationMemory:
    """Manages in-session conversation history."""
    
    def __init__(self, max_turns: int = 20):
        self.messages = []  # list of {"role": "user"|"assistant", "content": str}
        self.max_turns = max_turns
        self.summary = ""  # For Exercise 2: conversation summary
        self.turn_count = 0
    
    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        self.turn_count += 1
        
        # Keep only the last max_turns messages
        if len(self.messages) > self.max_turns * 2:
            self.messages = self.messages[-self.max_turns * 2:]
    
    def get_history(self, max_turns: int = None) -> list[dict]:
        """Get conversation history, optionally limited to last N turns."""
        if max_turns is None:
            return self.messages.copy()
        return self.messages[-max_turns * 2:] if self.messages else []
    
    def get_full_history(self) -> str:
        """Get full conversation as a string for summarization."""
        return "\n".join([f"{m['role'].upper()}: {m['content']}" for m in self.messages])
    
    def clear(self):
        self.messages = []
        self.summary = ""
        self.turn_count = 0
    
    def set_summary(self, summary: str):
        self.summary = summary
    
    def get_summary(self) -> str:
        return self.summary

# --- Medium-term memory (conversation summarization) ---

class SummarizingMemory(ConversationMemory):
    """Extends ConversationMemory with automatic summarization."""
    
    def __init__(self, max_turns: int = 20, summarize_after: int = 10):
        super().__init__(max_turns)
        self.summarize_after = summarize_after
        self._last_summary_turn = 0
    
    def add_message(self, role: str, content: str):
        super().add_message(role, content)
        
        # Check if we need to summarize
        if self.turn_count - self._last_summary_turn >= self.summarize_after:
            self._summarize_history()
    
    def _summarize_history(self):
        """Summarize older turns into a summary."""
        if len(self.messages) < self.summarize_after * 2:
            return
        
        # Get messages to summarize (all except last 10 turns)
        keep_turns = self.summarize_after  # keep last N turns
        messages_to_summarize = self.messages[:-keep_turns * 2] if self.messages else []
        
        if not messages_to_summarize:
            return
        
        # Build summary text
        history_text = "\n".join([
            f"{m['role'].upper()}: {m['content']}" for m in messages_to_summarize
        ])
        
        # Use LLM to generate summary
        from src.llm_client import chat_completion
        
        summary_prompt = f"""
        Summarize the following conversation between a student and a BVRIT chatbot.
        Preserve:
        - The user's name (if stated)
        - Which branches/topics they asked about
        - Key facts discussed (specific fee amounts, dates)
        - Any preferences stated (e.g., "I prefer CSE", "explain briefly")
        - Unresolved questions or follow-up threads
        
        Keep the summary concise (2-3 paragraphs max):
        
        {history_text}
        """
        
        try:
            summary_response, _ = chat_completion(
                messages=[
                    {"role": "system", "content": "You are a conversation summarizer. Create concise, informative summaries."},
                    {"role": "user", "content": summary_prompt}
                ],
                model=config.GENERATION_MODEL,
                temperature=0.3,
                max_tokens=300
            )
            self.summary = summary_response
        except Exception as e:
            # If summarization fails, keep what we have
            print(f"Summarization failed: {e}")
            self.summary = history_text[:500] + "..." if len(history_text) > 500 else history_text
        
        # Remove summarized messages, keep last N turns
        self.messages = self.messages[-keep_turns * 2:]
        self._last_summary_turn = self.turn_count

# --- Long-term memory (persistent user profiles) ---

class UserProfile:
    """User profile for cross-session memory."""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.name: Optional[str] = None
        self.branch_interest: Optional[str] = None
        self.language: str = "English"
        self.detail_level: str = "detailed"  # "detailed" or "brief"
        self.prior_topics: List[str] = []
        self.last_session_summary: str = ""
        self.fee_amounts_discussed: List[dict] = []
        self.scholarship_details: List[str] = []
        self.last_accessed: str = datetime.now().isoformat()
        self.created_at: str = datetime.now().isoformat()
        self.preferences: Dict[str, Any] = {}
    
    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "branch_interest": self.branch_interest,
            "language": self.language,
            "detail_level": self.detail_level,
            "prior_topics": self.prior_topics,
            "last_session_summary": self.last_session_summary,
            "fee_amounts_discussed": self.fee_amounts_discussed,
            "scholarship_details": self.scholarship_details,
            "last_accessed": self.last_accessed,
            "created_at": self.created_at,
            "preferences": self.preferences
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'UserProfile':
        profile = cls(data["user_id"])
        profile.name = data.get("name")
        profile.branch_interest = data.get("branch_interest")
        profile.language = data.get("language", "English")
        profile.detail_level = data.get("detail_level", "detailed")
        profile.prior_topics = data.get("prior_topics", [])
        profile.last_session_summary = data.get("last_session_summary", "")
        profile.fee_amounts_discussed = data.get("fee_amounts_discussed", [])
        profile.scholarship_details = data.get("scholarship_details", [])
        profile.last_accessed = data.get("last_accessed", datetime.now().isoformat())
        profile.created_at = data.get("created_at", datetime.now().isoformat())
        profile.preferences = data.get("preferences", {})
        return profile
    
    def update_from_conversation(self, conversation_summary: str):
        """Extract and update profile information from conversation."""
        # TODO: Use LLM to extract structured info from conversation
        # For now, we'll keep it simple
        self.last_session_summary = conversation_summary
        self.last_accessed = datetime.now().isoformat()

# --- Persistent storage ---

class ProfileStore:
    """SQLite-based persistent storage for user profiles."""
    
    def __init__(self, db_path: str = "user_profiles.db"):
        self.db_path = Path(db_path)
        self._init_db()
    
    def _init_db(self):
        """Initialize the database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    profile_data TEXT,
                    last_accessed TEXT,
                    created_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id)
                )
            """)
    
    def save_profile(self, profile: UserProfile):
        """Save or update a user profile."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_profiles (user_id, profile_data, last_accessed, created_at) VALUES (?, ?, ?, ?)",
                (
                    profile.user_id,
                    json.dumps(profile.to_dict()),
                    profile.last_accessed,
                    profile.created_at
                )
            )
    
    def load_profile(self, user_id: str) -> Optional[UserProfile]:
        """Load a user profile by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT profile_data FROM user_profiles WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if row:
                data = json.loads(row[0])
                return UserProfile.from_dict(data)
        return None
    
    def delete_profile(self, user_id: str) -> bool:
        """Delete a user profile and all associated data."""
        with sqlite3.connect(self.db_path) as conn:
            # Delete sessions first
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            # Delete profile
            cursor = conn.execute(
                "DELETE FROM user_profiles WHERE user_id = ?",
                (user_id,)
            )
            return cursor.rowcount > 0
    
    def delete_old_profiles(self, days: int = 30):
        """Delete profiles not accessed for N days (auto-expire)."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM user_profiles WHERE last_accessed < ?",
                (cutoff,)
            )
    
    def list_profiles(self) -> List[str]:
        """List all user IDs."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT user_id FROM user_profiles")
            return [row[0] for row in cursor.fetchall()]

# --- Session manager ---

class SessionManager:
    """Manages both short-term and long-term memory per session."""
    
    def __init__(self, session_id: str = None, user_id: str = None):
        self.session_id = session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.user_id = user_id or f"user_{hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]}"
        self.memory = SummarizingMemory(max_turns=20, summarize_after=10)
        self.profile_store = ProfileStore()
        self.profile: Optional[UserProfile] = None
        
        # Load profile if exists
        self._load_profile()
    
    def _load_profile(self):
        """Load user profile from persistent storage."""
        self.profile = self.profile_store.load_profile(self.user_id)
        if self.profile is None:
            self.profile = UserProfile(self.user_id)
            self.profile_store.save_profile(self.profile)
    
    def update_profile(self):
        """Save current profile to persistent storage."""
        if self.profile:
            self.profile_store.save_profile(self.profile)
    
    def clear_user_data(self):
        """Clear all data for this user (Right to be Forgotten)."""
        if self.profile:
            self.profile_store.delete_profile(self.profile.user_id)
            # Create new profile
            self.profile = UserProfile(self.user_id)
            self.profile_store.save_profile(self.profile)
            # Clear session memory
            self.memory.clear()
    
    def get_system_prompt_injection(self) -> str:
        """Get user-specific context for system prompt injection."""
        if not self.profile:
            return ""
        
        context = []
        
        if self.profile.name:
            context.append(f"The user's name is {self.profile.name}.")
        
        if self.profile.branch_interest:
            context.append(f"The user is interested in {self.profile.branch_interest}. When discussing fees, branches, or programs, default to answering about {self.profile.branch_interest} unless the user asks about something else.")
        
        if self.profile.language:
            context.append(f"The user prefers responses in {self.profile.language}.")
        
        if self.profile.detail_level:
            detail_desc = "detailed, comprehensive" if self.profile.detail_level == "detailed" else "brief, concise"
            context.append(f"The user prefers {detail_desc} answers. {'Provide thorough explanations with all available details.' if self.profile.detail_level == 'detailed' else 'Keep answers short and to the point. Use bullet points where possible.'}")
        
        if self.profile.prior_topics:
            topics = ", ".join(self.profile.prior_topics[-3:])
            context.append(f"The user has previously asked about: {topics}.")
        
        if self.profile.last_session_summary:
            context.append(f"Previous conversation summary: {self.profile.last_session_summary}")
        
        return "\n".join(context) if context else ""

# Global session manager
_current_session: Optional[SessionManager] = None

def get_session_manager(session_id: str = None, user_id: str = None) -> SessionManager:
    """Get or create a session manager.
    
    If a user_id is provided and differs from the current session's user_id,
    a new session manager is created for that user.
    """
    global _current_session
    if _current_session is None:
        _current_session = SessionManager(session_id, user_id)
    elif user_id is not None and _current_session.user_id != user_id:
        # User changed - create new session for this user
        _current_session = SessionManager(session_id, user_id)
    return _current_session

def reset_session():
    """Reset the current session."""
    global _current_session
    _current_session = None
