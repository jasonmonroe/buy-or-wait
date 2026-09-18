# tests/test_process_request.py
import pandas as pd
import pipelines.process_request as process_request_module
from pipelines.process_request import _check_id, run_process_request_pipeline
from src.usage_tracker import UsageTracker


class FakeLlmModel:
    def __init__(self):
        self.usage = UsageTracker()


class FakeRequestAgent:
    def __init__(self, model, dataset):
        self.model = model
        self.dataset = dataset
        self.processed = []

    def process_by_id(self, row):
        self.processed.append(row["request_id"])
        return {"request_id": row["request_id"], "amount_safe_to_pay": 100.0}


def _dataset_with_requests(request_ids):
    return {"requests": pd.DataFrame([{"request_id": rid} for rid in request_ids])}


# --------------------------------------------------------------------------- #
# _check_id
# --------------------------------------------------------------------------- #


def test_check_id_parses_value_from_id_key():
    assert _check_id({"id:3": True, "eval": False}) == 3


def test_check_id_none_when_bare_id_key_present():
    assert _check_id({"id": False}) is None


def test_check_id_none_when_absent():
    assert _check_id({"eval": True}) is None


# --------------------------------------------------------------------------- #
# run_process_request_pipeline
# --------------------------------------------------------------------------- #


def test_run_pipeline_processes_all_requests_when_no_id_given(monkeypatch):
    monkeypatch.setattr(process_request_module, "LlmModel", FakeLlmModel)
    monkeypatch.setattr(process_request_module, "RequestAgent", FakeRequestAgent)

    dataset = _dataset_with_requests(["request_1", "request_2", "request_3"])
    output_rows, usage = run_process_request_pipeline({}, dataset)

    assert [row["request_id"] for row in output_rows] == ["request_1", "request_2", "request_3"]
    assert isinstance(usage, UsageTracker)


def test_run_pipeline_processes_single_request_by_id(monkeypatch):
    monkeypatch.setattr(process_request_module, "LlmModel", FakeLlmModel)
    monkeypatch.setattr(process_request_module, "RequestAgent", FakeRequestAgent)

    dataset = _dataset_with_requests(["request_1", "request_2", "request_3"])
    output_rows, _ = run_process_request_pipeline({"id:1": True}, dataset)

    assert len(output_rows) == 1
    assert output_rows[0]["request_id"] == "request_2"


def test_run_pipeline_out_of_range_id_produces_no_rows(monkeypatch):
    monkeypatch.setattr(process_request_module, "LlmModel", FakeLlmModel)
    monkeypatch.setattr(process_request_module, "RequestAgent", FakeRequestAgent)

    dataset = _dataset_with_requests(["request_1"])
    output_rows, _ = run_process_request_pipeline({"id:99": True}, dataset)

    assert output_rows == []


def test_run_pipeline_returns_the_llm_models_usage_tracker(monkeypatch):
    monkeypatch.setattr(process_request_module, "LlmModel", FakeLlmModel)
    monkeypatch.setattr(process_request_module, "RequestAgent", FakeRequestAgent)

    dataset = _dataset_with_requests(["request_1"])
    _, usage = run_process_request_pipeline({}, dataset)

    usage.record(model="m", input_tokens=1, output_tokens=1)  # sanity: it's a live, usable tracker
    assert usage.totals().calls == 1
