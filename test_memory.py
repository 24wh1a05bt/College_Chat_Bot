# test_memory.py
"""
Test script for memory exercises.
Run with: python test_memory.py
"""
import sys
sys.path.append('.')

from src.rag_chain import answer, reset_session
from src.memory import reset_session as reset_memory_session

def test_exercise_1():
    """Test multi-turn conversation memory."""
    print("=== Exercise 1: Fix the Multi-Turn Failure ===\n")
    
    reset_session()
    reset_memory_session()
    
    test_script = [
        "What B.Tech branches does BVRIT offer?",
        "Tell me more about the first one.",
        "What's the fee for that branch?",
        "My name is Priya.",
        "What's my name and which branch was I asking about?"
    ]
    
    responses = []
    
    for i, query in enumerate(test_script, 1):
        print(f"Turn {i}: {query}")
        result = answer(query)
        print(f"Response: {result.answer[:200]}...\n")
        responses.append(result.answer)
        
        # Check criteria
        if i == 2:
            if "CSE" in result.answer or "Computer Science" in result.answer:
                print("✅ Turn 2 correctly identifies CSE as first branch")
            else:
                print("❌ Turn 2 does NOT identify CSE")
        
        if i == 3:
            if "fee" in result.answer.lower() and ("CSE" in result.answer or "Computer Science" in result.answer):
                print("✅ Turn 3 gives CSE's fee")
            else:
                print("❌ Turn 3 does NOT give CSE's fee")
        
        if i == 5:
            if "Priya" in result.answer and ("CSE" in result.answer or "Computer Science" in result.answer):
                print("✅ Turn 5 identifies Priya and CSE")
            else:
                print("❌ Turn 5 does NOT identify Priya and CSE")
        print("-" * 60)

def test_exercise_2():
    """Test long conversation summarization."""
    print("\n=== Exercise 2: Handle a 30-Turn Conversation ===\n")
    
    reset_session()
    reset_memory_session()
    
    # Simulate 20+ questions
    questions = [
        "What B.Tech branches does BVRIT offer?",
        "What is the fee for CSE?",
        "What is the fee for Mechanical?",
        "What is the fee for Civil?",
        "What is the fee for ECE?",
        "What is the fee for EEE?",
        "What is the fee for IT?",
        "What are the placement statistics for CSE?",
        "What are the placement statistics for Mechanical?",
        "What are the hostel facilities like?",
        "What are the faculty qualifications?",
        "What is the admission process?",
        "What are the eligibility criteria?",
        "What scholarships are available?",
        "What is the campus location?",
        "What are the lab facilities?",
        "What sports facilities are available?",
        "What is the library like?",
        "What is the college mission?",
        "What is the NIRF ranking?",
        "What is the accreditation status?",
        "What are the research opportunities?",
    ]
    
    print(f"Running {len(questions)} questions...")
    print("Check the token count difference in the code\n")
    
    # The summary should kick in after 10 turns
    for i, q in enumerate(questions[:15], 1):  # Test first 15
        result = answer(q)
        print(f"Turn {i}: {q[:50]}...")
        if i % 5 == 0:
            from src.memory import get_session_manager
            mgr = get_session_manager()
            print(f"  Memory turns: {len(mgr.memory.messages)}")
            if mgr.memory.get_summary():
                print(f"  Summary exists: {mgr.memory.get_summary()[:100]}...")
        print()

def test_exercise_3():
    """Test persistent memory across sessions."""
    print("\n=== Exercise 3: Persistent Memory Across Sessions ===\n")
    
    # Use a consistent user_id so the profile persists across sessions
    test_user_id = "user_priya_test"
    
    reset_session()
    reset_memory_session()
    
    print("--- Session 1 ---")
    queries = [
        "My name is Priya and I'm interested in B.Tech CSE.",
        "I prefer detailed answers in English."
    ]
    
    for q in queries:
        result = answer(q, user_id=test_user_id)
        print(f"Q: {q}")
        print(f"A: {result.answer[:200]}...\n")
    
    print("[Closing app...]")
    
    # Simulate new session (close app, reopen)
    reset_session()
    reset_memory_session()
    
    print("\n--- Session 2 (new app start) ---")
    queries = [
        "What's the fee for the branch I'm interested in?",
        "What's my name?"
    ]
    
    for q in queries:
        result = answer(q, user_id=test_user_id)
        print(f"Q: {q}")
        print(f"A: {result.answer}")
        print()
    
    # Check criteria
    from src.memory import get_session_manager
    mgr = get_session_manager(user_id=test_user_id)
    if mgr.profile.branch_interest:
        print(f"✅ Profile remembers branch: {mgr.profile.branch_interest}")
    else:
        print("❌ Profile does NOT remember branch")
    if mgr.profile.name:
        print(f"✅ Profile remembers name: {mgr.profile.name}")
    else:
        print("❌ Profile does NOT remember name")

def test_exercise_4():
    """Test personalization with different users."""
    print("\n=== Exercise 4: Personalise Responses ===\n")
    
    # Priya's profile
    print("--- Priya (CSE, detailed answers) ---")
    reset_session()
    reset_memory_session()
    
    # Set up Priya's profile
    from src.memory import get_session_manager
    mgr = get_session_manager(user_id="user_priya")
    mgr.profile.name = "Priya"
    mgr.profile.branch_interest = "CSE"
    mgr.profile.detail_level = "detailed"
    mgr.profile.language = "English"
    mgr.update_profile()
    
    result = answer("Tell me about my branch.", user_id="user_priya")
    print(f"Q: Tell me about my branch.")
    print(f"A: {result.answer}\n")
    print("Expected: Detailed paragraph about CSE")
    
    result = answer("What's the total 4-year cost?", user_id="user_priya")
    print(f"Q: What's the total 4-year cost?")
    print(f"A: {result.answer}\n")
    print("Expected: CSE fees")
    
    # Rahul's profile
    print("\n--- Rahul (Mechanical, brief answers) ---")
    reset_session()
    reset_memory_session()
    
    mgr = get_session_manager(user_id="user_rahul")
    mgr.profile.name = "Rahul"
    mgr.profile.branch_interest = "Mechanical"
    mgr.profile.detail_level = "brief"
    mgr.profile.language = "English"
    mgr.update_profile()
    
    result = answer("Tell me about my branch.", user_id="user_rahul")
    print(f"Q: Tell me about my branch.")
    print(f"A: {result.answer}\n")
    print("Expected: Brief bullets about Mechanical")
    
    result = answer("What's the total 4-year cost?", user_id="user_rahul")
    print(f"Q: What's the total 4-year cost?")
    print(f"A: {result.answer}\n")
    print("Expected: Mechanical fees")

def test_exercise_5():
    """Test privacy features."""
    print("\n=== Exercise 5: Right to Be Forgotten ===\n")
    
    reset_session()
    reset_memory_session()
    
    # Create profile
    print("--- Creating profile ---")
    from src.memory import get_session_manager
    mgr = get_session_manager(user_id="user_test")
    mgr.profile.name = "Test User"
    mgr.profile.branch_interest = "CSE"
    mgr.update_profile()
    
    # Verify profile exists
    mgr2 = get_session_manager(user_id="user_test")
    print(f"Profile exists: {mgr2.profile.name} is {mgr2.profile.branch_interest}")
    
    # Clear data
    print("\n--- Clearing data ---")
    result = answer("clear my data", user_id="user_test")
    print(f"Response: {result.answer}")
    
    # Verify cleared
    reset_session()
    reset_memory_session()
    mgr3 = get_session_manager(user_id="user_test")
    print(f"Profile after clear: {mgr3.profile.name} (should be None)")
    
    # Test privacy notice
    print("\n--- Privacy notice ---")
    result = answer("privacy policy")
    print(f"Response: {result.answer}")

if __name__ == "__main__":
    print("BVRIT Chatbot Memory Tests\n")
    print("=" * 70)
    
    test_exercise_1()
    print("\n" + "=" * 70)
    
    test_exercise_2()
    print("\n" + "=" * 70)
    
    test_exercise_3()
    print("\n" + "=" * 70)
    
    test_exercise_4()
    print("\n" + "=" * 70)
    
    test_exercise_5()