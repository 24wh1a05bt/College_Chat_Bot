"""
Phase 5, Dimension 08 - RAGAS scoring.

Runs faithfulness, answer_relevancy, context_precision, and context_recall
on the 08_ragas test cases using the RAGAS library. This runs as code,
not as an LLM-as-judge prompt, per the build brief.

Requires: pip install ragas datasets

Run with:
    python -m src.ragas_eval
"""
from __future__ import annotations

import json

from src import config


def run_ragas_eval() -> dict:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    results_path = config.EVAL_DIR / "judged_results.json"
    if not results_path.exists():
        raise FileNotFoundError(
            f"{results_path} not found. Run `python -m src.judge` first."
        )

    with open(results_path) as f:
        all_cases = json.load(f)

    ragas_cases = [c for c in all_cases if c["dimension"] == "08_ragas"]
    if not ragas_cases:
        print("No 08_ragas test cases found.")
        return {}

    dataset = Dataset.from_dict(
        {
            "question": [c["question"] for c in ragas_cases],
            "answer": [c["actual_answer"] for c in ragas_cases],
            "contexts": [[ch["text"] for ch in c["retrieved_chunks"]] for c in ragas_cases],
            "ground_truth": [c["expected_answer"] for c in ragas_cases],
        }
    )

    # RAGAS needs its own LLM/embeddings; route both through OpenRouter.
    ragas_llm = ChatOpenAI(
        model=config.JUDGE_MODEL,
        api_key=config.OPENROUTER_API_KEY,
        base_url=config.OPENROUTER_BASE_URL,
        temperature=0.0,
    )
    ragas_embeddings = OpenAIEmbeddings(
        model=config.EMBEDDING_MODEL,
        api_key=config.OPENROUTER_API_KEY,
        base_url=config.OPENROUTER_BASE_URL,
    )

    scored = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
    )

    df = scored.to_pandas()
    per_case = df.to_dict(orient="records")
    summary = {
        "faithfulness": float(df["faithfulness"].mean()),
        "answer_relevancy": float(df["answer_relevancy"].mean()),
        "context_precision": float(df["context_precision"].mean()),
        "context_recall": float(df["context_recall"].mean()),
    }

    output = {"summary": summary, "per_case": per_case}

    config.EVAL_DIR.mkdir(exist_ok=True)
    out_path = config.EVAL_DIR / "ragas_scores.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"RAGAS scores: {summary}")
    print(f"Saved -> {out_path}")
    return output


if __name__ == "__main__":
    run_ragas_eval()
