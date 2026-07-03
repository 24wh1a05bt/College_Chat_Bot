"""
Phase 5, Step B - Run the generated test suite against the live chatbot.

For every test case, captures: question, expected answer, actual response,
retrieved chunks (needed for RAGAS), and latency. Writes
eval_results/run_results.json.

Run with:
    python -m src.test_runner
"""
from __future__ import annotations

import json

from src import config
from src.rag_chain import answer


def _run_single_turn(case: dict) -> dict:
    result = answer(case["question"])
    return {
        **case,
        "actual_answer": result.answer,
        "retrieved_chunks": [
            {"text": c.text, "section": c.section, "page": c.page} for c in result.chunks
        ],
        "latency_seconds": result.latency_seconds,
        "refused": result.refused,
    }


def _run_multi_turn(case: dict) -> dict:
    turns = case["turns"]
    history = []
    actual_answers = []
    latencies = []
    last_chunks = []

    for turn in turns:
        result = answer(turn, chat_history=history)
        actual_answers.append(result.answer)
        latencies.append(result.latency_seconds)
        last_chunks = result.chunks
        history.append({"role": "user", "content": turn})
        history.append({"role": "assistant", "content": result.answer})

    return {
        **case,
        "actual_answer": actual_answers[-1],
        "actual_turns": actual_answers,
        "retrieved_chunks": [
            {"text": c.text, "section": c.section, "page": c.page} for c in last_chunks
        ],
        "latency_seconds": sum(latencies),
        "refused": False,
    }


def run_test_suite() -> list[dict]:
    cases_path = config.EVAL_DIR / "test_cases.json"
    if not cases_path.exists():
        raise FileNotFoundError(
            f"{cases_path} not found. Run `python -m src.test_generator` first."
        )

    with open(cases_path) as f:
        cases = json.load(f)

    results = []
    for case in cases:
        print(f"Running {case['id']} ({case['dimension']})...")
        if case.get("dimension") == "07_context" or "turns" in case:
            results.append(_run_multi_turn(case))
        else:
            results.append(_run_single_turn(case))

    config.EVAL_DIR.mkdir(exist_ok=True)
    out_path = config.EVAL_DIR / "run_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Ran {len(results)} test cases -> {out_path}")
    return results


if __name__ == "__main__":
    run_test_suite()
