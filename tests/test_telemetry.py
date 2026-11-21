"""Проверки процессной телеметрии: LLM, tools, промпты, токены."""

from __future__ import annotations

from types import SimpleNamespace

from src import telemetry
from src.llm import OpenAILLM
from src.prompts import load_prompt, prompt_meta


class _Usage:
    prompt_tokens = 120
    completion_tokens = 30
    prompt_tokens_details = SimpleNamespace(cached_tokens=10)


class _Response:
    choices = [SimpleNamespace(message=SimpleNamespace(content="ok"))]
    usage = _Usage()


class _Completions:
    def create(self, **kwargs):
        return _Response()


class _FailingCompletions:
    def create(self, **kwargs):
        raise TimeoutError("provider timeout")


class _Client:
    chat = SimpleNamespace(completions=_Completions())


def test_llm_usage_and_tokens_are_recorded():
    telemetry.start_run()
    try:
        llm = OpenAILLM(client=_Client(), model="test-model")
        assert llm._plain(system="system", user="user") == "ok"
        snapshot = telemetry.snapshot()
    finally:
        telemetry.stop_run()

    assert snapshot["llm_calls"] == 1
    assert snapshot["tokens"]["input_tokens"] == 120
    assert snapshot["tokens"]["output_tokens"] == 30
    assert snapshot["tokens"]["cached_tokens"] == 10
    assert snapshot["total_tokens"] == 150
    assert snapshot["llm_latency_sec"] >= 0
    assert snapshot["llm_events"][0]["schema"] == "plain"
    assert snapshot["llm_events"][0]["model"] == "test-model"


def test_failed_llm_attempt_is_recorded():
    telemetry.start_run()
    try:
        llm = OpenAILLM(
            client=SimpleNamespace(
                chat=SimpleNamespace(completions=_FailingCompletions())
            ),
            model="test-model",
        )
        try:
            llm._plain(system="system", user="user")
        except TimeoutError:
            pass
        snapshot = telemetry.snapshot()
    finally:
        telemetry.stop_run()

    assert snapshot["llm_calls"] == 0
    assert snapshot["llm_attempts"] == 1
    assert snapshot["llm_errors"] == 1
    assert snapshot["llm_events"][0]["status"] == "error"


def test_tool_decorator_records_name_status_and_time():
    telemetry.start_run()
    try:
        @telemetry.timed_tool("dummy_tool")
        def tool():
            return "value"

        assert tool() == "value"
        snapshot = telemetry.snapshot()
    finally:
        telemetry.stop_run()

    assert snapshot["tool_calls"] == 1
    assert snapshot["tool_names"] == ["dummy_tool"]
    assert snapshot["tool_latency_sec"] >= 0


def test_prompt_version_is_recorded():
    telemetry.start_run()
    try:
        load_prompt("router")
        snapshot = telemetry.snapshot()
    finally:
        telemetry.stop_run()

    meta = prompt_meta("router")
    assert snapshot["prompts"] == [
        {"id": "router", "version": meta["version"], "hash": meta["hash"]}
    ]
