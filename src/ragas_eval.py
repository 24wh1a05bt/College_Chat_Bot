"""
Phase 5, Dimension 08 - RAGAS scoring.

Runs faithfulness, answer_relevancy, context_precision, and context_recall
on the 08_ragas test cases using the RAGAS library. This runs as code,
not as an LLM-as-judge prompt, per the build brief.

Supports both the modern ragas API (>=0.2, EvaluationDataset + wrapped
llm/embeddings + renamed columns) and the legacy API (<=0.1, raw
datasets.Dataset + question/answer/contexts/ground_truth columns), falling
back automatically if the modern import path isn't available.

Also works around a known ragas/langchain_community version-mismatch bug:
older ragas releases unconditionally import
`langchain_community.chat_models.vertexai.ChatVertexAI` just to register it
as one of several optional LLM backends, even though this project never
uses Vertex AI. Newer langchain_community releases no longer ship that
module, which crashes the import before any of our code runs. We patch a
harmless stub into sys.modules ahead of time so the import succeeds
regardless of which ragas/langchain_community versions are installed.

Requires: pip install ragas datasets langchain-openai

Run with:
    python -m src.ragas_eval
"""
from __future__ import annotations

import json
import sys
import types

from src import config

# RAGAS's internal LLM calls default to a very high max_tokens (16384 in
# recent versions). On metered providers like OpenRouter with limited
# credits, that triggers a 402 "insufficient credits" error on every single
# scoring call, silently producing NaN for every metric. Capping this well
# below the account's available token budget fixes it without needing to
# add credits. Override via RAGAS_LLM_MAX_TOKENS in .env if needed.
import os
RAGAS_LLM_MAX_TOKENS = int(os.getenv("RAGAS_LLM_MAX_TOKENS", "1000"))


def _patch_missing_vertexai_stub() -> None:
    """Insert a no-op langchain_community.chat_models.vertexai.ChatVertexAI
    into sys.modules if the real one isn't importable. This is a pure
    import-time shim: it is never instantiated or used, because this
    project never configures a Vertex AI model. It only exists so that
    `from langchain_community.chat_models.vertexai import ChatVertexAI`
    (which some ragas versions run eagerly, unconditionally, at import
    time) doesn't crash the whole process on environments where that
    optional module was dropped from langchain_community."""
    module_name = "langchain_community.chat_models.vertexai"
    if module_name in sys.modules:
        return
    try:
        import langchain_community.chat_models.vertexai  # noqa: F401
        return  # real module is available - nothing to patch
    except ModuleNotFoundError:
        pass

    stub = types.ModuleType(module_name)

    class ChatVertexAI:  # placeholder only - never actually used
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "This is a stub ChatVertexAI inserted only to satisfy an "
                "eager ragas import. This project does not support Vertex "
                "AI as an LLM backend."
            )

    stub.ChatVertexAI = ChatVertexAI
    sys.modules[module_name] = stub

    try:
        import langchain_community.chat_models as _chat_models
        _chat_models.vertexai = stub
    except ModuleNotFoundError:
        pass


def _import_ragas_metrics():
    """Import ragas.metrics in isolation so a broken/outdated install still
    produces a clear, actionable message instead of a raw traceback if the
    stub above doesn't cover some other missing optional dependency."""
    _patch_missing_vertexai_stub()
    try:
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
        return answer_relevancy, context_precision, context_recall, faithfulness
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "Failed to import ragas.metrics even after patching the known "
            "vertexai import issue. This usually means another optional "
            "ragas dependency is missing. Try:\n\n"
            "    pip install -U ragas datasets langchain langchain-community langchain-openai\n\n"
            f"Original error: {e}"
        ) from e


def run_ragas_eval() -> dict:
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

    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    answer_relevancy, context_precision, context_recall, faithfulness = _import_ragas_metrics()

    # RAGAS needs its own LLM/embeddings; route both through OpenRouter.
    # max_tokens is capped explicitly - see RAGAS_LLM_MAX_TOKENS note above.
    ragas_llm_raw = ChatOpenAI(
        model=config.JUDGE_MODEL,
        api_key=config.OPENROUTER_API_KEY,
        base_url=config.OPENROUTER_BASE_URL,
        temperature=0.0,
        max_tokens=RAGAS_LLM_MAX_TOKENS,
    )
    ragas_embeddings_raw = OpenAIEmbeddings(
        model=config.EMBEDDING_MODEL,
        api_key=config.OPENROUTER_API_KEY,
        base_url=config.OPENROUTER_BASE_URL,
    )

    df = None

    # --- Try the modern ragas (>=0.2) API first -------------------------------
    try:
        from ragas import evaluate, EvaluationDataset
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper

        ragas_llm = LangchainLLMWrapper(ragas_llm_raw)
        ragas_embeddings = LangchainEmbeddingsWrapper(ragas_embeddings_raw)

        dataset = EvaluationDataset.from_list(
            [
                {
                    "user_input": c["question"],
                    "response": c["actual_answer"],
                    "retrieved_contexts": [ch["text"] for ch in c["retrieved_chunks"]],
                    "reference": c["expected_answer"],
                }
                for c in ragas_cases
            ]
        )

        scored = evaluate(
            dataset=dataset,
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
            llm=ragas_llm,
            embeddings=ragas_embeddings,
        )
        df = scored.to_pandas()
        print("Scored using modern RAGAS API (EvaluationDataset).")

    except (ImportError, TypeError, AttributeError, ValueError) as e:
        # --- Fall back to the legacy ragas (<=0.1) API --------------------
        print(f"Modern RAGAS API unavailable ({type(e).__name__}: {e}); "
              f"falling back to legacy Dataset API.")
        try:
            from datasets import Dataset
            from ragas import evaluate

            dataset = Dataset.from_dict(
                {
                    "question": [c["question"] for c in ragas_cases],
                    "answer": [c["actual_answer"] for c in ragas_cases],
                    "contexts": [[ch["text"] for ch in c["retrieved_chunks"]] for c in ragas_cases],
                    "ground_truth": [c["expected_answer"] for c in ragas_cases],
                }
            )

            scored = evaluate(
                dataset,
                metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
                llm=ragas_llm_raw,
                embeddings=ragas_embeddings_raw,
            )
            df = scored.to_pandas()
            print("Scored using legacy RAGAS API (datasets.Dataset).")

        except Exception as legacy_error:
            print(f"Legacy RAGAS API also failed ({type(legacy_error).__name__}: "
                  f"{legacy_error}). Skipping RAGAS scoring.")
            return {}

    if df is None or df.empty:
        print("RAGAS returned no scored rows. Skipping.")
        return {}

    # Warn (rather than silently report NaN) if any metric failed to score -
    # e.g. due to provider rate limits, credit exhaustion, or timeouts.
    import math
    for metric_name in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
        if metric_name in df.columns and df[metric_name].isna().all():
            print(f"WARNING: '{metric_name}' scored NaN for every case — the "
                  f"underlying LLM calls likely failed (check OpenRouter "
                  f"credits/rate limits). See scores below.")

    per_case = df.to_dict(orient="records")
    summary = {}
    for metric_name in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
        if metric_name in df.columns:
            values = df[metric_name].dropna()
            summary[metric_name] = float(values.mean()) if not values.empty else float("nan")

    output = {"summary": summary, "per_case": per_case}

    config.EVAL_DIR.mkdir(exist_ok=True)
    out_path = config.EVAL_DIR / "ragas_scores.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"RAGAS scores: {summary}")
    print(f"Saved -> {out_path}")
    return output


if __name__ == "__main__":
    try:
        run_ragas_eval()
    except RuntimeError as e:
        print(f"\n{e}\n")