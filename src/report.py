"""
Phase 5, Step D - Generate the structured evaluation report.

Combines judged_results.json + ragas_scores.json into a single
evaluation_report.json consumed by the Streamlit evaluation dashboard,
plus a human-readable evaluation_report.md.

Run with:
    python -m src.report
"""
from __future__ import annotations

import json

from src import config

DIMENSION_LABELS = {
    "01_functional": "01 Functional",
    "02_quality": "02 Quality",
    "03_safety": "03 Safety",
    "04_security": "04 Security",
    "05_robustness": "05 Robustness",
    "06_performance": "06 Performance",
    "07_context": "07 Context",
    "08_ragas": "08 RAGAS",
}


def _load(name: str, default=None):
    path = config.EVAL_DIR / name
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)


def build_report() -> dict:
    judged = _load("judged_results.json", [])
    ragas = _load("ragas_scores.json", {"summary": {}, "per_case": []})

    per_dimension = {dim: {"passed": 0, "failed": 0, "warning": 0, "total": 0, "cases": []}
                      for dim in DIMENSION_LABELS}

    ragas_summary = ragas.get("summary", {})
    # RAGAS pass threshold: all four metrics >= 0.7 counts the case as passed.
    ragas_pass = all(v >= 0.7 for v in ragas_summary.values()) if ragas_summary else False

    for case in judged:
        dim = case["dimension"]
        bucket = per_dimension.setdefault(dim, {"passed": 0, "failed": 0, "warning": 0, "total": 0, "cases": []})
        bucket["total"] += 1

        if dim == "08_ragas":
            verdict = "pass" if ragas_pass else "fail"
        else:
            verdict = case.get("judge_verdict", {}).get("verdict", "warning")

        if verdict == "pass":
            bucket["passed"] += 1
        elif verdict == "fail":
            bucket["failed"] += 1
        else:
            bucket["warning"] += 1

        bucket["cases"].append(
            {
                "id": case.get("id"),
                "question": case.get("question") or case.get("turns"),
                "expected_answer": case.get("expected_answer"),
                "actual_answer": case.get("actual_answer"),
                "verdict": verdict,
                "reason": case.get("judge_verdict", {}).get("reason", ""),
                "root_cause": case.get("judge_verdict", {}).get("root_cause", ""),
                "suggested_fix": case.get("judge_verdict", {}).get("suggested_fix", ""),
                "latency_seconds": case.get("latency_seconds"),
            }
        )

    total = sum(b["total"] for b in per_dimension.values())
    passed = sum(b["passed"] for b in per_dimension.values())
    failed = sum(b["failed"] for b in per_dimension.values())
    warning = sum(b["warning"] for b in per_dimension.values())
    pass_rate = round(100 * passed / total, 1) if total else 0.0

    # Weakest dimension = lowest pass ratio among dimensions with cases.
    weakest_dim, weakest_ratio = None, 1.1
    for dim, b in per_dimension.items():
        if b["total"] == 0:
            continue
        ratio = b["passed"] / b["total"]
        if ratio < weakest_ratio:
            weakest_ratio = ratio
            weakest_dim = dim

    fix_map = {
        "01_functional": "Tighten the output-format instructions in the grounding prompt (citation syntax, completeness checklist).",
        "02_quality": "Increase top_k or reduce chunk_size so exact figures aren't split across chunk boundaries.",
        "03_safety": "Add explicit disclaimers to the system prompt for outcome-related questions (placements, admissions).",
        "04_security": "Strengthen the system prompt with explicit injection-defense instructions and treat user input as untrusted.",
        "05_robustness": "Add input validation (empty/too-long/non-text) before calling the retriever.",
        "06_performance": "Reduce top_k, cache embeddings, or switch to a faster generation model.",
        "07_context": "Include more prior turns in the chat history sent to the LLM, or add coreference resolution.",
        "08_ragas": "Context Precision is often the lowest metric — reduce chunk_size or add stricter metadata filtering.",
    }

    report = {
        "summary": {
            "total_test_cases": total,
            "passed": passed,
            "failed": failed,
            "warning": warning,
            "pass_rate_pct": pass_rate,
        },
        "per_dimension": {
            DIMENSION_LABELS[dim]: {
                "passed": b["passed"],
                "failed": b["failed"],
                "warning": b["warning"],
                "total": b["total"],
                "cases": b["cases"],
            }
            for dim, b in per_dimension.items()
        },
        "weakest_dimension": DIMENSION_LABELS.get(weakest_dim, "N/A"),
        "recommended_fix": fix_map.get(weakest_dim, "Review failing cases manually."),
        "ragas_scores": ragas_summary,
        "ragas_diagnosis": (
            "Context Precision is the lowest RAGAS metric — retrieval returns some "
            "irrelevant chunks. Consider reducing chunk_size or adding metadata filters."
            if ragas_summary and ragas_summary.get("context_precision", 1) == min(
                ragas_summary.values(), default=1
            )
            else ""
        ),
    }

    config.EVAL_DIR.mkdir(exist_ok=True)
    out_path = config.EVAL_DIR / "evaluation_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    _write_markdown(report)
    print(f"Report written -> {out_path}")
    return report


def _write_markdown(report: dict) -> None:
    s = report["summary"]
    lines = [
        "# BVRIT FAQ Chatbot — Evaluation Report",
        "",
        "## Summary",
        f"Total test cases: {s['total_test_cases']} | Passed: {s['passed']} | "
        f"Failed: {s['failed']} | Warning: {s['warning']} | Pass rate: {s['pass_rate_pct']}%",
        "",
        "## Per-dimension breakdown",
    ]
    for dim, b in report["per_dimension"].items():
        lines.append(f"- **{dim}**: {b['passed']}/{b['total']} passed")

    lines += [
        "",
        f"**Weakest dimension:** {report['weakest_dimension']}",
        f"**Recommended fix:** {report['recommended_fix']}",
        "",
        "## RAGAS scores",
    ]
    for k, v in report.get("ragas_scores", {}).items():
        lines.append(f"- {k}: {v:.2f}")
    if report.get("ragas_diagnosis"):
        lines.append("")
        lines.append(f"**RAGAS diagnosis:** {report['ragas_diagnosis']}")

    (config.EVAL_DIR / "evaluation_report.md").write_text("\n".join(lines))


if __name__ == "__main__":
    build_report()
