"""M15: the fallback chain (Gemini → Gemini backup → Groq) and the Groq client, with fakes and an
httpx mock transport. No network."""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.errors import (
    AnswerBlockedError,
    LLMNotConfiguredError,
    LLMUnavailableError,
    QuotaExhaustedError,
    RateLimitedError,
)
from app.services import rag
from app.services.llm import FallbackLLM, GroqClient, build_chain, build_llm
from app.services.llm.base import LLMResult
from app.services.llm.rate_limiter import TokenBucket
from tests.helpers import make_settings

# --- the chain ---------------------------------------------------------------------------------


class Fake:
    def __init__(self, model, *, error=None, pieces=("Hello ", "there.")):
        self.model, self.error, self.pieces = model, error, pieces
        self.calls: list[dict] = []
        self.closed = 0

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return LLMResult("answer", self.model, "stop")

    def stream(self, *, system, prompt):
        self.calls.append({"stream": True})
        try:
            if self.error:
                raise self.error
            yield from self.pieces
            yield LLMResult("".join(self.pieces), self.model, "stop")
        finally:
            self.closed += 1


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def test_the_first_model_that_answers_wins_and_backups_are_marked():
    lite, flash = Fake("lite"), Fake("flash")
    llm = FallbackLLM([lite, flash])
    r = llm.generate(system="s", prompt="p", model="utility")
    assert (r.model, r.fallback) == ("lite", False) and flash.calls == []
    assert lite.calls[0]["model"] == "utility"  # the override applies to the first model


@pytest.mark.parametrize("error", [QuotaExhaustedError("q"), LLMUnavailableError("u"),
                                   RateLimitedError("r"), LLMNotConfiguredError("n")])  # fmt: skip
def test_quota_outage_limits_and_configuration_move_on_to_the_next_model(error):
    lite, flash = Fake("lite", error=error), Fake("flash")
    r = FallbackLLM([lite, flash]).generate(system="s", prompt="p", model="utility")
    assert (r.model, r.fallback) == ("flash", True)
    assert flash.calls[0]["model"] is None  # a backup uses its own model


def test_a_safety_block_is_not_routed_around():
    lite, flash = Fake("lite", error=AnswerBlockedError("blocked")), Fake("flash")
    with pytest.raises(AnswerBlockedError):
        FallbackLLM([lite, flash]).generate(system="s", prompt="p")
    assert flash.calls == []


def test_when_every_model_fails_the_last_error_is_reported():
    chain = FallbackLLM([Fake("a", error=QuotaExhaustedError("a")),
                         Fake("b", error=QuotaExhaustedError("b, too"))])  # fmt: skip
    with pytest.raises(QuotaExhaustedError, match="b, too"):
        chain.generate(system="s", prompt="p")


def test_a_spent_daily_quota_is_skipped_until_the_cooldown_ends():
    clock = Clock()
    lite, flash = Fake("lite", error=QuotaExhaustedError("q")), Fake("flash")
    llm = FallbackLLM([lite, flash], clock=clock, cooldown=900)
    llm.generate(system="s", prompt="p")
    llm.generate(system="s", prompt="p")
    assert len(lite.calls) == 1  # the second question didn't try it
    clock.now = 901
    llm.generate(system="s", prompt="p")
    assert len(lite.calls) == 2  # tried again after the cooldown
    unavailable = Fake("lite", error=LLMUnavailableError("u"))
    llm = FallbackLLM([unavailable, Fake("flash")], clock=Clock())
    llm.generate(system="s", prompt="p")
    llm.generate(system="s", prompt="p")
    assert len(unavailable.calls) == 2  # an outage isn't a spent quota: no cooldown


def test_streams_switch_only_before_the_first_piece():
    lite, groq = Fake("lite", error=QuotaExhaustedError("q")), Fake("groq")
    out = list(FallbackLLM([lite, groq]).stream(system="s", prompt="p"))
    assert out[:-1] == ["Hello ", "there."] and out[-1].fallback and out[-1].model == "groq"
    assert lite.closed == 1


class FailsMidway(Fake):
    def stream(self, *, system, prompt):
        yield "Half an "
        raise LLMUnavailableError("gone")


def test_a_stream_that_fails_after_text_is_not_retried_elsewhere():
    backup = Fake("flash")
    stream = FallbackLLM([FailsMidway("lite"), backup]).stream(system="s", prompt="p")
    assert next(stream) == "Half an "
    with pytest.raises(LLMUnavailableError):
        next(stream)
    assert backup.calls == []


def test_the_chain_is_built_in_order_from_settings():
    settings = make_settings(groq_api_key="fake-groq-key")
    assert [p.model for p in build_chain(settings)] == [
        "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "openai/gpt-oss-120b"]  # fmt: skip
    assert isinstance(build_llm(settings), FallbackLLM)
    only = make_settings(gemini_model_fallback=None)
    assert [p.model for p in build_chain(only)] == ["gemini-3.5-flash-lite"]
    assert not isinstance(build_llm(only), FallbackLLM)


def test_a_backup_answer_carries_a_notice():
    assert "backup model (openai/gpt-oss-120b)" in rag.fallback_notice("openai/gpt-oss-120b")


# --- the Groq client ------------------------------------------------------------------------------


def groq(handler, **kwargs):
    t = Clock()
    return GroqClient(
        api_key="test-key", model=kwargs.get("model", "openai/gpt-oss-120b"), temperature=0.1,
        max_output_tokens=512, timeout_seconds=25, max_retries=2,
        limiter=TokenBucket(600, burst=5, clock=t, sleep=lambda s: None),
        transport=httpx.MockTransport(handler), clock=t, sleep=lambda s: None,
    )  # fmt: skip


def completion(text="Ten days [1].", finish="stop"):
    return {"model": "openai/gpt-oss-120b",
            "choices": [{"message": {"content": text}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 12}}  # fmt: skip


def test_groq_generate_sends_an_openai_style_request_and_reads_the_reply():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json=completion())

    r = groq(handler).generate(system="RULES", prompt="SOURCES", max_output_tokens=256)
    assert (r.text, r.prompt_tokens, r.output_tokens, r.finish_reason) == (
        "Ten days [1].", 900, 12, "stop")  # fmt: skip
    body = seen[0]
    assert body["messages"] == [{"role": "system", "content": "RULES"},
                                {"role": "user", "content": "SOURCES"}]  # fmt: skip
    assert body["reasoning_effort"] == "low" and body["max_completion_tokens"] == 256 + 1024


def test_groq_json_mode_describes_the_schema():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=completion('{"standalone_question": "Q?"}'))

    groq(handler, model="qwen/qwen3.8-27b").generate(
        system="S", prompt="P", json_schema={"type": "object"}
    )
    body = seen[0]
    assert (
        body["response_format"] == {"type": "json_object"}
        and "JSON Schema" in body["messages"][0]["content"]
    )
    assert "reasoning_effort" not in body  # not a reasoning model


@pytest.mark.parametrize(
    ("status", "message", "expected"),
    [
        (429, "Rate limit reached on tokens per day (TPD)", QuotaExhaustedError),
        (429, "Rate limit reached on requests per day (RPD)", QuotaExhaustedError),
        (401, "Invalid API Key", LLMNotConfiguredError),
        (404, "model not found", LLMNotConfiguredError),
        (400, "bad request", LLMUnavailableError),
    ],
)
def test_groq_errors_are_classified_without_retrying(status, message, expected):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json={"error": {"message": message}})

    with pytest.raises(expected):
        groq(handler).generate(system="s", prompt="p")
    assert len(calls) == 1


def test_groq_per_minute_limits_and_outages_are_retried():
    limited = httpx.Response(429, headers={"retry-after": "2"}, json={"error": {"message": "TPM"}})
    replies = [limited, httpx.Response(503, json={}), httpx.Response(200, json=completion())]
    r = groq(lambda request: replies.pop(0)).generate(system="s", prompt="p")
    assert r.attempts == 3 and r.text == "Ten days [1]."


def test_groq_stream_yields_text_then_the_result():
    events = [{"model": "openai/gpt-oss-120b", "choices": [{"delta": {"content": "Ten "}}]},
              {"choices": [{"delta": {"content": "days."}, "finish_reason": "stop"}]},
              {"choices": [],
               "x_groq": {"usage": {"prompt_tokens": 800, "completion_tokens": 3}}}]  # fmt: skip
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    out = list(groq(lambda request: httpx.Response(200, text=body)).stream(system="s", prompt="p"))
    assert out[:-1] == ["Ten ", "days."]
    final = out[-1]
    assert (final.text, final.prompt_tokens, final.output_tokens) == ("Ten days.", 800, 3)
    assert {"first_token", "generate", "rate_limit_wait"} <= set(final.timings_ms)


def test_groq_empty_answer_is_an_error():
    with pytest.raises(LLMUnavailableError):
        groq(lambda request: httpx.Response(200, json=completion("  "))).generate(
            system="s", prompt="p"
        )
