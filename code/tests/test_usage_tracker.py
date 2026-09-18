# tests/test_usage_tracker.py
from src.usage_tracker import ModelUsage, UsageTracker


def test_model_usage_total_tokens():
    usage = ModelUsage(calls=2, input_tokens=100, output_tokens=50)
    assert usage.total_tokens == 150


def test_record_accumulates_per_model():
    tracker = UsageTracker()
    tracker.record(model="gemini-3.8-flash", input_tokens=100, output_tokens=20)
    tracker.record(model="gemini-3.8-flash", input_tokens=200, output_tokens=30)

    by_model = tracker.by_model()
    assert set(by_model) == {"gemini-3.8-flash"}
    usage = by_model["gemini-3.8-flash"]
    assert usage.calls == 2
    assert usage.input_tokens == 300
    assert usage.output_tokens == 50


def test_record_separates_different_models():
    tracker = UsageTracker()
    tracker.record(model="model-a", input_tokens=10, output_tokens=5)
    tracker.record(model="model-b", input_tokens=20, output_tokens=15)

    by_model = tracker.by_model()
    assert set(by_model) == {"model-a", "model-b"}
    assert by_model["model-a"].calls == 1
    assert by_model["model-b"].calls == 1


def test_totals_aggregates_across_models():
    tracker = UsageTracker()
    tracker.record(model="model-a", input_tokens=10, output_tokens=5)
    tracker.record(model="model-b", input_tokens=20, output_tokens=15)

    overall = tracker.totals()
    assert overall.calls == 2
    assert overall.input_tokens == 30
    assert overall.output_tokens == 20
    assert overall.total_tokens == 50


def test_totals_empty_tracker():
    tracker = UsageTracker()
    overall = tracker.totals()
    assert overall.calls == 0
    assert overall.total_tokens == 0


def test_by_model_dict_is_a_shallow_copy():
    tracker = UsageTracker()
    tracker.record(model="model-a", input_tokens=1, output_tokens=1)
    snapshot = tracker.by_model()
    snapshot["model-b"] = ModelUsage(calls=5)  # adding a key to the snapshot...
    assert "model-b" not in tracker.by_model()  # ...must not leak into the tracker
