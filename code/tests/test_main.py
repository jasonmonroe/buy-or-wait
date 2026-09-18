# tests/test_main.py
import main as main_module
from main import _parse_args, run_main_pipeline
from src.usage_tracker import UsageTracker


class FakeDataHandler:
    instances = []

    def __init__(self, args):
        self.args = args
        self.__dict__["saved"] = None
        FakeDataHandler.instances.append(self)

    def save(self, output_rows):
        self.saved = output_rows


# --------------------------------------------------------------------------- #
# _parse_args
# --------------------------------------------------------------------------- #


def test_parse_args_boolean_flags():
    parsed = _parse_args(["--eda", "--sample"])
    assert parsed["eda"] is True
    assert parsed["eval"] is False
    assert parsed["sample"] is True


def test_parse_args_id_flag_present():
    parsed = _parse_args(["--id:7"])
    assert parsed["id:7"] is True
    assert "id" not in parsed


def test_parse_args_id_flag_absent_falls_back_to_bare_key():
    parsed = _parse_args([])
    assert parsed["id"] is False


def test_parse_args_no_flags():
    parsed = _parse_args([])
    assert parsed == {"eda": False, "eval": False, "sample": False, "id": False}


# --------------------------------------------------------------------------- #
# run_main_pipeline
# --------------------------------------------------------------------------- #


def test_run_main_pipeline_saves_output_and_skips_eval_by_default(monkeypatch):
    FakeDataHandler.instances.clear()
    monkeypatch.setattr(main_module, "DataHandler", FakeDataHandler)
    monkeypatch.setattr(
        main_module,
        "run_process_request_pipeline",
        lambda args, dataset: ([{"request_id": "request_1"}], UsageTracker()),
    )
    eval_calls = []
    monkeypatch.setattr(
        main_module, "run_evaluation_pipeline", lambda usage, request_count: eval_calls.append(request_count)
    )

    run_main_pipeline({"eval": False})

    assert FakeDataHandler.instances[0].saved == [{"request_id": "request_1"}]
    assert eval_calls == []


def test_run_main_pipeline_runs_eval_when_requested(monkeypatch):
    FakeDataHandler.instances.clear()
    monkeypatch.setattr(main_module, "DataHandler", FakeDataHandler)
    monkeypatch.setattr(
        main_module,
        "run_process_request_pipeline",
        lambda args, dataset: ([{"request_id": "request_1"}, {"request_id": "request_2"}], UsageTracker()),
    )
    eval_calls = []
    monkeypatch.setattr(
        main_module, "run_evaluation_pipeline", lambda usage, request_count: eval_calls.append(request_count)
    )

    run_main_pipeline({"eval": True})

    assert eval_calls == [2]
