# Memory Exercises - Implementation Status

## Exercise 1: Fix Multi-Turn Failure
- [x] Conversation history management (messages list)
- [x] Full message history sent to API
- [x] Query rewriter for coreference resolution (newly added)
- [ ] Test with 5-turn script (Turn 2 failed previously due to poor retrieval for "the first one")
- [ ] Verify all 5 turns pass criteria

## Exercise 2: Handle 30-Turn Conversation
- [x] Simulate long conversation tracking
- [x] Summarization strategy (after every 10 turns)
- [x] Summary preserves user name, topics, facts, preferences
- [ ] Test with 20+ questions
- [ ] Report token count before/after

## Exercise 3: Persistent Memory Across Sessions
- [x] User profile schema (JSON structure in profile_schema.py)
- [x] SQLite persistent store
- [x] Load profile at session start
- [ ] Fix test to use consistent user_id across sessions
- [ ] Test cross-session scenario

## Exercise 4: Personalise Responses
- [x] Two user profiles with different preferences
- [x] System prompt injection with user context
- [x] Different responses per user
- [ ] Document system prompt differences

## Exercise 5: Right to Be Forgotten
- [x] "Clear my data" command
- [x] Profile deletion
- [x] Auto-expire rule (30 days)
- [x] Privacy notice on first interaction
- [x] Field classification (ESSENTIAL/NICE-TO-HAVE/SENSITIVE)