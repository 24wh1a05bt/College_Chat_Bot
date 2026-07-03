"""
Runs the complete Phase 5 evaluation pipeline in order:
  1. Generate test cases (LLM #1)
  2. Run them against the live chatbot (LLM #2)
  3. Judge expected vs actual (LLM #3)
  4. Score RAGAS dimension programmatically
  5. Compile the final evaluation report

Requires the index to already be built (see src/ingest.py or the app sidebar).

Run with:
    python run_evaluation.py
"""
from src.ingest import get_collection
from src.test_generator import generate_test_cases
from src.test_runner import run_test_suite
from src.judge import judge_all
from src.report import build_report


def main():
    if get_collection().count() == 0:
        raise SystemExit(
            "Index is empty. Run `python -m src.ingest --rebuild` (or use the "
            "Streamlit sidebar) before running the evaluation pipeline."
        )

    print("=== Step A: generating test cases ===")
    generate_test_cases()

    print("\n=== Step B: running test suite against chatbot ===")
    run_test_suite()

    print("\n=== Step C: judging results ===")
    judge_all()

    print("\n=== Dimension 08: RAGAS scoring ===")
    try:
        from ragas_eval import run_ragas_eval
        run_ragas_eval()
    except ImportError:
        print("ragas/datasets not installed — skipping RAGAS scoring "
              "(pip install ragas datasets). Report will omit RAGAS scores.")

    print("\n=== Step D: compiling report ===")
    report = build_report()
    print(f"\nDone. Pass rate: {report['summary']['pass_rate_pct']}%  "
          f"Weakest dimension: {report['weakest_dimension']}")


if __name__ == "__main__":
    main()
