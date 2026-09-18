# tests/test_request_agent.py
from datetime import date

import agents.request_agent as request_agent_module
import pandas as pd
import pytest
from agents.request_agent import RequestAgent

from tests.factories import empty_exchange_rates, empty_images, empty_messages, make_events_df, make_payment_options


class FakeModel:
    def __init__(self, response=None):
        self.response = response if response is not None else {}
        self.calls = []

    def get_response(self, prompt: str):
        self.calls.append(prompt)
        return self.response


class FakeCtx:
    """Stand-in for a rules_engine.FinancialContext - just the attributes
    RequestAgent reads off of it."""

    def __init__(self, **kwargs):
        defaults = dict(
            home_currency="ZAR",
            minimum_balance_to_keep=1000.0,
            amount_safe_to_pay=500.0,
            affordability_status="affordable_now",
            recommended_payment_method="full_payment",
            payment_plan="2024-01-01:500",
            earliest_date_for_full_payment="2024-01-01",
            spending_changes_needed="none",
        )
        defaults.update(kwargs)
        self.__dict__.update(defaults)


def make_dataset() -> dict:
    return {
        "exchange_rates": empty_exchange_rates(),
        "financial_events": make_events_df([{"user_id": "user_1"}]),
        "financial_profiles": pd.DataFrame([{"user_id": "user_1", "home_currency": "ZAR"}]),
        "images": empty_images(),
        "messages": empty_messages(),
        "request_payment_options": make_payment_options([{"request_id": "request_1"}]),
        "requests": pd.DataFrame([{"request_id": "request_1"}]),
    }


def make_agent(model=None) -> RequestAgent:
    return RequestAgent(model or FakeModel(), make_dataset())


def make_row(**overrides) -> pd.Series:
    defaults = dict(
        request_id="request_1",
        user_id="user_1",
        request_date=date(2024, 1, 1),
        request_type="purchase",
        requested_amount=500.0,
        desired_completion_date=date(2024, 2, 1),
        allows_partial_payment=True,
        request_text="Can I afford this?",
    )
    defaults.update(overrides)
    return pd.Series(defaults)


# --------------------------------------------------------------------------- #
# _set_attrs / filter
# --------------------------------------------------------------------------- #


def test_set_attrs_only_sets_known_fields():
    agent = make_agent()
    agent._set_attrs(make_row(unknown_field="ignored"))
    assert agent.request_id == "request_1"
    assert not hasattr(agent, "unknown_field")


def test_filter_scopes_events_and_options_to_this_request_and_user():
    dataset = make_dataset()
    dataset["financial_events"] = make_events_df(
        [{"user_id": "user_1"}, {"user_id": "user_2"}]
    )
    dataset["request_payment_options"] = make_payment_options(
        [{"request_id": "request_1"}, {"request_id": "request_other"}]
    )
    agent = RequestAgent(FakeModel(), dataset)
    agent._set_attrs(make_row())

    filtered = agent.filter()

    assert len(filtered["financial_events"]) == 1
    assert filtered["financial_events"].iloc[0]["user_id"] == "user_1"
    assert len(filtered["request_payment_options"]) == 1


def test_filter_keeps_full_event_history_even_with_unrelated_messages():
    # Regression test: financial_events must NOT be narrowed down to only
    # events referenced by a message - the forecast needs the user's whole
    # history regardless of what messages exist.
    dataset = make_dataset()
    dataset["financial_events"] = make_events_df(
        [{"event_id": "event_a", "user_id": "user_1"}, {"event_id": "event_b", "user_id": "user_1"}]
    )
    dataset["messages"] = pd.DataFrame(
        [
            {
                "message_id": "message_1", "user_id": "user_1", "request_id": "request_1",
                "related_event_id": "event_a", "sent_at": None, "source_type": "employer",
                "message_text": "...",
            }
        ]
    )
    agent = RequestAgent(FakeModel(), dataset)
    agent._set_attrs(make_row())

    filtered = agent.filter()

    assert len(filtered["financial_events"]) == 2


# --------------------------------------------------------------------------- #
# apply_rules / get_* accessors
# --------------------------------------------------------------------------- #


def test_apply_rules_populates_attrs_from_ctx(monkeypatch):
    agent = make_agent()
    agent._set_attrs(make_row())
    fake_ctx = FakeCtx()
    monkeypatch.setattr(request_agent_module.rules_engine, "compute", lambda *a, **k: fake_ctx)

    result = agent.apply_rules({})

    assert agent.amount_safe_to_pay == 500.0
    assert agent.affordability_status == "affordable_now"
    assert agent.recommended_payment_method == "full_payment"
    assert agent.payment_plan == "2024-01-01:500"
    assert agent.earliest_date_for_full_payment == "2024-01-01"
    assert agent.spending_changes_needed == "none"
    assert result["amount_safe_to_pay"] == 500.0


# --------------------------------------------------------------------------- #
# get_decision_explanation
# --------------------------------------------------------------------------- #


def test_get_decision_explanation_uses_offline_fallback_when_no_api_key(monkeypatch):
    monkeypatch.setattr(request_agent_module, "MODEL_API_KEY", None)
    agent = make_agent()
    agent._set_attrs(make_row())
    agent._ctx = FakeCtx()
    agent.amount_safe_to_pay = 500.0
    agent.recommended_payment_method = "full_payment"
    agent.payment_plan = "2024-01-01:500"

    explanation = agent.get_decision_explanation()

    assert "Full Payment" in explanation
    assert "ZAR 1,000" in explanation


def test_get_decision_explanation_uses_model_response_when_api_key_set(monkeypatch):
    monkeypatch.setattr(request_agent_module, "MODEL_API_KEY", "fake-key")
    model = FakeModel(response={"decision_explanation": "Pay ZAR 500 today."})
    agent = make_agent(model=model)
    agent._set_attrs(make_row())
    agent._ctx = FakeCtx()
    agent.amount_safe_to_pay = 500.0
    agent.recommended_payment_method = "full_payment"
    agent.payment_plan = "2024-01-01:500"

    explanation = agent.get_decision_explanation()

    assert explanation == "Pay ZAR 500 today."
    assert len(model.calls) == 1


def test_get_decision_explanation_falls_back_when_model_returns_no_key(monkeypatch):
    monkeypatch.setattr(request_agent_module, "MODEL_API_KEY", "fake-key")
    model = FakeModel(response={})  # missing "decision_explanation"
    agent = make_agent(model=model)
    agent._set_attrs(make_row())
    agent._ctx = FakeCtx()
    agent.amount_safe_to_pay = 500.0
    agent.recommended_payment_method = "full_payment"
    agent.payment_plan = "2024-01-01:500"

    explanation = agent.get_decision_explanation()

    assert "Full Payment" in explanation  # offline template


def test_fallback_explanation_not_recommended_case(monkeypatch):
    monkeypatch.setattr(request_agent_module, "MODEL_API_KEY", None)
    agent = make_agent()
    agent._set_attrs(make_row())
    agent._ctx = FakeCtx()
    agent.recommended_payment_method = "not_recommended"

    explanation = agent.get_decision_explanation()

    assert "Do not proceed" in explanation


# --------------------------------------------------------------------------- #
# get_output / check_rules
# --------------------------------------------------------------------------- #


def test_get_output_returns_all_eight_columns_in_order():
    agent = make_agent()
    agent._set_attrs(make_row())
    agent.amount_safe_to_pay = 500.0
    agent.affordability_status = "affordable_now"
    agent.recommended_payment_method = "full_payment"
    agent.payment_plan = "2024-01-01:500"
    agent.earliest_date_for_full_payment = "2024-01-01"
    agent.spending_changes_needed = "none"
    agent.decision_explanation = "Pay ZAR 500 today."

    output = agent.get_output()

    assert list(output.keys()) == [
        "request_id", "amount_safe_to_pay", "affordability_status",
        "recommended_payment_method", "payment_plan", "earliest_date_for_full_payment",
        "spending_changes_needed", "decision_explanation",
    ]


def test_check_rules_true_for_a_consistent_affordable_now_result():
    agent = make_agent()
    agent._set_attrs(make_row())
    agent.amount_safe_to_pay = 500.0
    agent.affordability_status = "affordable_now"
    agent.recommended_payment_method = "full_payment"
    agent.payment_plan = "2024-01-01:500"
    agent.earliest_date_for_full_payment = "2024-01-01"
    agent.spending_changes_needed = "none"
    agent.decision_explanation = "Pay ZAR 500 today."

    assert agent.check_rules() is True


def test_check_rules_false_when_amount_out_of_bounds():
    agent = make_agent()
    agent._set_attrs(make_row())
    agent.amount_safe_to_pay = 999999.0  # exceeds requested_amount
    agent.affordability_status = "affordable_now"
    agent.recommended_payment_method = "full_payment"
    agent.payment_plan = "2024-01-01:999999"
    agent.earliest_date_for_full_payment = "2024-01-01"
    agent.spending_changes_needed = "none"
    agent.decision_explanation = "..."

    assert agent.check_rules() is False


def test_check_rules_false_when_affordable_now_earliest_date_mismatched():
    agent = make_agent()
    agent._set_attrs(make_row())
    agent.amount_safe_to_pay = 500.0
    agent.affordability_status = "affordable_now"
    agent.recommended_payment_method = "full_payment"
    agent.payment_plan = "2024-01-01:500"
    agent.earliest_date_for_full_payment = "2024-05-01"  # should equal request_date
    agent.spending_changes_needed = "none"
    agent.decision_explanation = "..."

    assert agent.check_rules() is False


def test_check_rules_allows_blank_earliest_date_for_not_affordable():
    agent = make_agent()
    agent._set_attrs(make_row())
    agent.amount_safe_to_pay = 0.0
    agent.affordability_status = "not_affordable"
    agent.recommended_payment_method = "not_recommended"
    agent.payment_plan = "none"
    agent.earliest_date_for_full_payment = ""  # legitimately blank, not None
    agent.spending_changes_needed = "none"
    agent.decision_explanation = "..."

    assert agent.check_rules() is True


def test_check_rules_false_when_a_required_field_is_none():
    agent = make_agent()
    agent._set_attrs(make_row())
    agent.amount_safe_to_pay = 500.0
    # affordability_status left as None
    assert agent.check_rules() is False


# --------------------------------------------------------------------------- #
# process_by_id (integration of the whole per-request flow)
# --------------------------------------------------------------------------- #


def test_process_by_id_returns_output_row(monkeypatch):
    monkeypatch.setattr(request_agent_module, "MODEL_API_KEY", None)
    agent = make_agent()
    fake_ctx = FakeCtx()
    monkeypatch.setattr(request_agent_module.rules_engine, "compute", lambda *a, **k: fake_ctx)

    output = agent.process_by_id(make_row())

    assert output["request_id"] == "request_1"
    assert output["amount_safe_to_pay"] == 500.0
    assert output["decision_explanation"]


def test_process_by_id_prints_warning_when_check_rules_fails(monkeypatch, capsys):
    monkeypatch.setattr(request_agent_module, "MODEL_API_KEY", None)
    agent = make_agent()
    # A ctx whose affordability_status is affordable_now but whose earliest
    # date doesn't match request_date - fails check_rules().
    fake_ctx = FakeCtx(earliest_date_for_full_payment="2099-01-01")
    monkeypatch.setattr(request_agent_module.rules_engine, "compute", lambda *a, **k: fake_ctx)

    agent.process_by_id(make_row())

    assert "check_rules() failed" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# OCR / amount extraction
# --------------------------------------------------------------------------- #


def test_get_amount_from_image_returns_none_when_no_images():
    agent = make_agent()
    assert agent.get_amount_from_image(empty_images()) is None


def test_get_amount_from_image_parses_ocr_text(monkeypatch):
    agent = make_agent()
    images = pd.DataFrame([{"image_id": "image_1", "user_id": "u", "request_id": "r", "related_event_id": "e"}])

    monkeypatch.setattr(agent, "extract_from_image", lambda imgs: "Total: ZAR 4,200.00 due")

    assert agent.get_amount_from_image(images) == 4200.0


def test_extract_from_image_returns_empty_string_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(request_agent_module, "IMAGE_DIR", str(tmp_path) + "/")
    agent = make_agent()
    images = pd.DataFrame([{"image_id": "does_not_exist", "user_id": "u", "request_id": "r", "related_event_id": "e"}])

    assert agent.extract_from_image(images) == ""


def test_extract_from_image_calls_pytesseract_when_file_exists(tmp_path, monkeypatch):
    image_path = tmp_path / "image_1.png"
    image_path.write_bytes(b"not a real png, just needs to exist")
    monkeypatch.setattr(request_agent_module, "IMAGE_DIR", str(tmp_path) + "/")
    monkeypatch.setattr(request_agent_module.pytesseract, "image_to_string", lambda img: "ZAR 100")
    monkeypatch.setattr(request_agent_module.Image, "open", lambda path: "fake-image-handle")

    agent = make_agent()
    images = pd.DataFrame([{"image_id": "image_1", "user_id": "u", "request_id": "r", "related_event_id": "e"}])

    assert agent.extract_from_image(images) == "ZAR 100"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Total: ZAR 4,200.00 due", 4200.0),
        ("no numbers here", None),
        ("", None),
        (None, None),
        ("Qty 2 at ZAR 50 = ZAR 100", 100.0),  # picks the largest candidate
    ],
)
def test_parse_amount_from_text(text, expected):
    agent = make_agent()
    assert agent._parse_amount_from_text(text) == expected
