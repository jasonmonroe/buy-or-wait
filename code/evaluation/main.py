# evaluation/main.py
# +---------------------------------------------------------------------------+
# |                          EVALUTATION PIPELINE                             |
# +---------------------------------------------------------------------------+
#
# Writes evaluation/usage_report.md, the token-usage/cost report required in
# code.zip (see README.md "Token Usage And Cost Analysis"). Numbers here come
# straight from the UsageTracker each LlmModel call records its real
# response.usage into during the run - never estimated after the fact.

import inspect
from datetime import datetime, timezone
from pathlib import Path

from src.constants import MILLION, MODEL_PRICING, USAGE_REPORT_FILE
from src.usage_tracker import ModelUsage, UsageTracker


def run_evaluation_pipeline(usage: UsageTracker, request_count: int) -> None:
    m = inspect.currentframe().f_code.co_name.title().replace("_", " ").upper()
    print(f"\n🏃 {m}")

    report = _build_usage_report(usage, request_count)

    output_path = Path(USAGE_REPORT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)

    print(f"📊 Wrote {output_path}")


def _cost(model_usage: ModelUsage, pricing: dict | None) -> float | None:
    if (
        not pricing
        or pricing.get("input_per_million") is None
        or pricing.get("output_per_million") is None
    ):
        return None
    return (
        model_usage.input_tokens / MILLION * pricing["input_per_million"]
        + model_usage.output_tokens / MILLION * pricing["output_per_million"]
    )


def _fmt_cost(cost: float | None) -> str:
    return f"${cost:,.4f}" if cost is not None else "N/A (pricing not configured)"


def _build_usage_report(usage: UsageTracker, request_count: int) -> str:
    by_model = usage.by_model()
    overall = usage.totals()

    lines = [
        "# Token Usage & Cost Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"Requests processed in this run: {request_count}",
        "",
        "## Per-Model Breakdown",
        "",
        "| Model | Calls | Input Tokens | Output Tokens | Total Tokens | Estimated Cost |",
        "|---|---|---|---|---|---|",
    ]

    if not by_model:
        lines.append("| (no model calls made this run) | 0 | 0 | 0 | 0 | $0.00 |")
    else:
        for model in sorted(by_model):
            model_usage = by_model[model]
            cost = _cost(model_usage, MODEL_PRICING.get(model))
            lines.append(
                f"| {model} | {model_usage.calls} | {model_usage.input_tokens:,} | "
                f"{model_usage.output_tokens:,} | {model_usage.total_tokens:,} | {_fmt_cost(cost)} |"
            )

    per_model_costs = [_cost(by_model[m], MODEL_PRICING.get(m)) for m in by_model]
    total_cost = (
        sum(per_model_costs)
        if by_model and all(c is not None for c in per_model_costs)
        else None
    )
    avg_tokens_per_request = (
        overall.total_tokens / request_count if request_count else 0.0
    )
    cost_per_request = (
        total_cost / request_count if total_cost is not None and request_count else None
    )

    lines += [
        "",
        "## Overall Totals",
        "",
        f"- Total model calls: {overall.calls}",
        f"- Total input tokens: {overall.input_tokens:,}",
        f"- Total output tokens: {overall.output_tokens:,}",
        f"- Total tokens: {overall.total_tokens:,}",
        f"- Average tokens per request: {avg_tokens_per_request:,.1f}",
        f"- Estimated total cost: {_fmt_cost(total_cost)}",
        f"- Estimated cost per request: {_fmt_cost(cost_per_request)}",
    ]

    if request_count and overall.calls < request_count:
        skipped = request_count - overall.calls
        lines += [
            "",
            (
                f"Note: {skipped} of {request_count} requests made no model call "
                "(MODEL_API_KEY unset, or the offline fallback template was used "
                "for decision_explanation)."
            ),
        ]

    missing_pricing = sorted(
        m for m in by_model if MODEL_PRICING.get(m, {}).get("input_per_million") is None
    )
    if missing_pricing:
        lines += [
            "",
            (
                f"Note: pricing not configured for: {', '.join(missing_pricing)}. Add "
                "real per-1M-token rates to MODEL_PRICING in src/constants.py to "
                "compute cost."
            ),
        ]

    return "\n".join(lines) + "\n"
