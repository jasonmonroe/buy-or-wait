# tests/test_evaluation_main.py
import evaluation.main as evaluation_module
from evaluation.main import run_evaluation_pipeline
from src.usage_tracker import UsageTracker


def test_run_evaluation_pipeline_writes_report(tmp_path, monkeypatch):
    report_path = tmp_path / "evaluation" / "usage_report.md"
    monkeypatch.setattr(evaluation_module, "USAGE_REPORT_FILE", str(report_path))

    tracker = UsageTracker()
    tracker.record(model="gemini-3.8-flash", input_tokens=1000, output_tokens=200)

    run_evaluation_pipeline(tracker, request_count=25)

    content = report_path.read_text()
    assert "gemini-3.8-flash" in content
    assert "Requests processed in this run: 25" in content


def test_report_no_calls_made_is_honest_about_it():
    tracker = UsageTracker()
    report = evaluation_module._build_usage_report(tracker, request_count=10)

    assert "no model calls made this run" in report
    assert "Total model calls: 0" in report
    assert "10 of 10 requests made no model call" in report


def test_report_computes_cost_when_pricing_configured(monkeypatch):
    monkeypatch.setitem(
        evaluation_module.MODEL_PRICING,
        "test-model",
        {"input_per_million": 1.0, "output_per_million": 2.0},
    )
    tracker = UsageTracker()
    tracker.record(model="test-model", input_tokens=1_000_000, output_tokens=500_000)

    report = evaluation_module._build_usage_report(tracker, request_count=1)

    # 1M input @ $1/M + 0.5M output @ $2/M = $2.00
    assert "Estimated total cost: $2.0000" in report
    assert "Estimated cost per request: $2.0000" in report


def test_report_reports_cost_unavailable_when_pricing_missing():
    tracker = UsageTracker()
    tracker.record(model="unpriced-model", input_tokens=100, output_tokens=50)

    report = evaluation_module._build_usage_report(tracker, request_count=1)

    assert "N/A (pricing not configured)" in report
    assert "pricing not configured for: unpriced-model" in report


def test_report_partial_pricing_across_models_leaves_total_unavailable(monkeypatch):
    monkeypatch.setitem(
        evaluation_module.MODEL_PRICING,
        "priced-model",
        {"input_per_million": 1.0, "output_per_million": 1.0},
    )
    tracker = UsageTracker()
    tracker.record(model="priced-model", input_tokens=1000, output_tokens=1000)
    tracker.record(model="unpriced-model", input_tokens=1000, output_tokens=1000)

    report = evaluation_module._build_usage_report(tracker, request_count=2)

    assert "Estimated total cost: N/A (pricing not configured)" in report


def test_report_average_tokens_per_request_and_zero_requests_guard():
    tracker = UsageTracker()
    tracker.record(model="m", input_tokens=100, output_tokens=100)

    report = evaluation_module._build_usage_report(tracker, request_count=0)

    assert "Average tokens per request: 0.0" in report


def test_cost_returns_none_without_pricing():
    from src.usage_tracker import ModelUsage

    assert evaluation_module._cost(ModelUsage(input_tokens=100, output_tokens=50), None) is None


def test_fmt_cost_formats_dollar_amount():
    assert evaluation_module._fmt_cost(1.5) == "$1.5000"


def test_fmt_cost_none_is_not_configured():
    assert evaluation_module._fmt_cost(None) == "N/A (pricing not configured)"
