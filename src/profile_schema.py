# src/profile_schema.py
"""
User Profile Schema Documentation
For Exercise 3: Design user profile schema
"""

USER_PROFILE_SCHEMA = {
    "user_id": {
        "type": "string",
        "required": True,
        "description": "Unique identifier for the user",
        "classification": "ESSENTIAL"
    },
    "name": {
        "type": "string",
        "required": False,
        "description": "User's name for personalization",
        "classification": "ESSENTIAL"
    },
    "branch_interest": {
        "type": "string",
        "required": False,
        "description": "User's branch of interest (e.g., CSE, Mechanical)",
        "classification": "ESSENTIAL"
    },
    "language": {
        "type": "string",
        "required": False,
        "default": "English",
        "description": "User's preferred language",
        "classification": "NICE-TO-HAVE"
    },
    "detail_level": {
        "type": "string",
        "required": False,
        "default": "detailed",
        "enum": ["detailed", "brief"],
        "description": "User's preference for answer detail",
        "classification": "NICE-TO-HAVE"
    },
    "prior_topics": {
        "type": "array",
        "items": {"type": "string"},
        "required": False,
        "description": "Topics the user has previously asked about",
        "classification": "NICE-TO-HAVE"
    },
    "last_session_summary": {
        "type": "string",
        "required": False,
        "description": "Summary of previous conversation",
        "classification": "NICE-TO-HAVE"
    },
    "fee_amounts_discussed": {
        "type": "array",
        "items": {"type": "object"},
        "required": False,
        "description": "Fee amounts discussed with the user",
        "classification": "ESSENTIAL"
    },
    "scholarship_details": {
        "type": "array",
        "items": {"type": "string"},
        "required": False,
        "description": "Scholarships the user has asked about",
        "classification": "NICE-TO-HAVE"
    },
    "full_conversation_transcripts": {
        "type": "array",
        "items": {"type": "object"},
        "required": False,
        "description": "Full conversation transcripts (not stored for privacy)",
        "classification": "SENSITIVE"
    },
    "preferences": {
        "type": "object",
        "required": False,
        "description": "Additional user preferences",
        "classification": "NICE-TO-HAVE"
    },
    "last_accessed": {
        "type": "string",
        "required": True,
        "description": "Last access timestamp (for auto-expire)",
        "classification": "ESSENTIAL"
    },
    "created_at": {
        "type": "string",
        "required": True,
        "description": "Profile creation timestamp",
        "classification": "ESSENTIAL"
    }
}

def print_schema():
    """Print the user profile schema with classifications."""
    print("=== User Profile Schema ===\n")
    print(f"{'Field':<30} {'Classification':<15} {'Required':<10} Description")
    print("-" * 80)
    
    for field, details in USER_PROFILE_SCHEMA.items():
        print(f"{field:<30} {details['classification']:<15} {str(details.get('required', False)):<10} {details['description']}")
    
    print("\n\n=== Classification Legend ===")
    print("ESSENTIAL: Needed for personalization")
    print("NICE-TO-HAVE: Improves experience but not critical")
    print("SENSITIVE: Should not be stored or needs extra protection")

if __name__ == "__main__":
    print_schema()