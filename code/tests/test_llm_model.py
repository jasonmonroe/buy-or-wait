# tests/test_llm_model.py
from types import SimpleNamespace

import httpx
import models.llm_model as llm_model_module
import pytest
from models.llm_model import LlmModel
from openai import InternalServerError, RateLimitError


def make_response(content, model="gemini-3.8-flash", prompt_tokens=10, completion_tokens=5, usage=True):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=(
            SimpleNamespace(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )
            if usage
            else None
        ),
        model=model,
    )


def make_error(cls, message="error", status_code=429, body=None):
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(status_code, request=request)
    return cls(message, response=response, body=body)


@pytest.fixture()
def model(monkeypatch):
    monkeypatch.setattr(llm_model_module, "MODEL_API_KEY", "fake-key")
    monkeypatch.setattr(llm_model_module, "MODEL_API_URL", "https://example.com")
    monkeypatch.setattr(llm_model_module.time, "sleep", lambda *_: None)
    return LlmModel()


def test_get_response_parses_plain_json_and_records_usage(model, monkeypatch):
    response = make_response('{"decision_explanation": "Pay now."}')
    monkeypatch.setattr(model._client.chat.completions, "create", lambda **kwargs: response)

    result = model.get_response("prompt")

    assert result == {"decision_explanation": "Pay now."}
    usage = model.usage.by_model()["gemini-3.8-flash"]
    assert usage.calls == 1
    assert usage.input_tokens == 10
    assert usage.output_tokens == 5


def test_get_response_strips_markdown_code_fence(model, monkeypatch):
    response = make_response('```json\n{"decision_explanation": "Pay now."}\n```')
    monkeypatch.setattr(model._client.chat.completions, "create", lambda **kwargs: response)

    assert model.get_response("prompt") == {"decision_explanation": "Pay now."}


def test_get_response_handles_missing_usage_gracefully(model, monkeypatch):
    response = make_response('{"decision_explanation": "ok"}', usage=False)
    monkeypatch.setattr(model._client.chat.completions, "create", lambda **kwargs: response)

    model.get_response("prompt")

    assert model.usage.totals().calls == 0


def test_get_response_internal_server_error_returns_empty_dict(model, monkeypatch):
    def raise_error(**kwargs):
        raise make_error(InternalServerError, status_code=503)

    monkeypatch.setattr(model._client.chat.completions, "create", raise_error)
    assert model.get_response("prompt") == {}


def test_get_response_retries_rate_limit_then_succeeds(model, monkeypatch):
    calls = {"count": 0}

    def flaky_create(**kwargs):
        calls["count"] += 1
        if calls["count"] < 2:
            raise make_error(RateLimitError, body={"error": {"message": "please retry in 1s"}})
        return make_response('{"decision_explanation": "ok"}')

    monkeypatch.setattr(model._client.chat.completions, "create", flaky_create)

    assert model.get_response("prompt") == {"decision_explanation": "ok"}
    assert calls["count"] == 2


def test_get_response_rate_limit_exhausts_retries(model, monkeypatch):
    def always_rate_limited(**kwargs):
        raise make_error(RateLimitError, body={"error": {"message": "please retry in 1s"}})

    monkeypatch.setattr(model._client.chat.completions, "create", always_rate_limited)

    assert model.get_response("prompt") == {"error": True}


def test_get_response_rate_limit_body_as_list(model, monkeypatch):
    def rate_limited_list_body(**kwargs):
        raise make_error(RateLimitError, body=[{"error": {"message": "please retry in 1s"}}])

    monkeypatch.setattr(model._client.chat.completions, "create", rate_limited_list_body)

    assert model.get_response("prompt") == {"error": True}


def test_get_response_unexpected_exception_returns_empty_dict(model, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(model._client.chat.completions, "create", boom)
    assert model.get_response("prompt") == {}


# --------------------------------------------------------------------------- #
# _parse_delay_time
# --------------------------------------------------------------------------- #


def test_parse_delay_time_extracts_seconds(model):
    assert model._parse_delay_time("Please retry in 2.5s") == 2.5


def test_parse_delay_time_falls_back_when_anchor_missing(model):
    assert model._parse_delay_time("no timing info here") == llm_model_module.RATE_LIMIT_PAUSE_TIMER


def test_parse_delay_time_caps_overly_long_delay(model):
    huge_delay = llm_model_module.RATE_LIMIT_PAUSE_TIMER * 10
    message = f"please retry in {huge_delay}s"
    assert model._parse_delay_time(message) == llm_model_module.RATE_LIMIT_PAUSE_TIMER


# --------------------------------------------------------------------------- #
# _filter_response
# --------------------------------------------------------------------------- #


def test_filter_response_empty_content_returns_empty_dict(model):
    assert model._filter_response(make_response("")) == {}


def test_filter_response_invalid_json_returns_empty_dict(model):
    assert model._filter_response(make_response("not json at all")) == {}


def test_filter_response_auto_repairs_missing_closing_brace(model):
    result = model._filter_response(make_response('{"decision_explanation": "cut off"'))
    assert result == {"decision_explanation": "cut off"}


def test_filter_response_reads_content_attribute_when_no_choices(model):
    response = SimpleNamespace(content='{"decision_explanation": "direct"}')
    assert model._filter_response(response) == {"decision_explanation": "direct"}


def test_filter_response_falls_back_to_str_for_unknown_type(model):
    class Weird:
        def __str__(self):
            return '{"decision_explanation": "stringified"}'

    assert model._filter_response(Weird()) == {"decision_explanation": "stringified"}


def test_filter_response_accepts_plain_string(model):
    assert model._filter_response('{"decision_explanation": "raw string"}') == {
        "decision_explanation": "raw string"
    }
