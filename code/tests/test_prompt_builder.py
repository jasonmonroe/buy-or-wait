# tests/test_prompt_builder.py
import json

from src.prompt_builder import PromptBuilder


def test_prompt_embeds_payload_as_json():
    payload = {"request_id": "request_1", "amount_safe_to_pay": 100.0}
    builder = PromptBuilder(payload)

    assert "request_1" in builder.prompt
    assert "100.0" in builder.prompt
    assert "decision_explanation" in builder.prompt


def test_prompt_serializes_non_json_native_values_via_str():
    from datetime import date

    payload = {"earliest_date_for_full_payment": date(2024, 1, 1)}
    builder = PromptBuilder(payload)

    assert "2024-01-01" in builder.prompt
