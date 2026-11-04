"""Claude API を偽の HTTP 応答に差し替えて、選別と要約の呼び出しを確かめる。"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import anthropic
import httpx2
import pytest

from ai_dev_digest.llm import JUDGE_BATCH_SIZE, SUMMARY_INPUT_CHARS, ClaudeSummarizer, LLMError
from tests.conftest import entry


def message(text: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    """Messages API の応答の形。text はモデルが返す本文。"""
    content = [{"type": "text", "text": text}] if text else []
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


def summarizer(
    respond: Callable[[dict[str, Any]], httpx2.Response], model: str = "claude-sonnet-5-5"
) -> tuple[ClaudeSummarizer, list[dict[str, Any]]]:
    """respond にリクエストの本文 (JSON) を渡して応答を決める Summarizer と、本文の記録。"""
    requests: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        requests.append(body)
        return respond(body)

    client = anthropic.Anthropic(
        api_key="test-key",
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
        max_retries=0,
    )
    return ClaudeSummarizer(client, model=model), requests


def test_judge_returns_scores_of_relevant_entries_only() -> None:
    judged = {
        "items": [
            {"index": 0, "relevant": True, "score": 80},
            {"index": 1, "relevant": False, "score": 10},
        ]
    }
    llm, requests = summarizer(lambda _body: httpx2.Response(200, json=message(json.dumps(judged))))
    entries = [
        entry(url="https://example.com/a"),
        entry(url="https://example.com/b", title="Event"),
    ]

    assert llm.judge(entries) == {"https://example.com/a": 80}
    assert len(requests) == 1
    assert requests[0]["model"] == "claude-sonnet-5-5"
    assert requests[0]["output_config"]["effort"] == "low"
    assert "[1] 発信元: Example\n題名: Event" in requests[0]["messages"][0]["content"]


def test_judge_ignores_an_index_outside_the_batch() -> None:
    judged = {"items": [{"index": 5, "relevant": True, "score": 80}]}
    llm, _ = summarizer(lambda _body: httpx2.Response(200, json=message(json.dumps(judged))))

    assert llm.judge([entry()]) == {}


def test_judge_splits_many_entries_into_batches() -> None:
    def respond(body: dict[str, Any]) -> httpx2.Response:
        count = body["messages"][0]["content"].count("\n題名: ")
        items = [{"index": i, "relevant": True, "score": 1} for i in range(count)]
        return httpx2.Response(200, json=message(json.dumps({"items": items})))

    llm, requests = summarizer(respond)
    entries = [entry(url=f"https://example.com/{i}") for i in range(JUDGE_BATCH_SIZE + 1)]

    assert len(llm.judge(entries)) == JUDGE_BATCH_SIZE + 1
    assert len(requests) == 2


def test_judge_returns_nothing_for_no_entries() -> None:
    llm, requests = summarizer(lambda _body: httpx2.Response(500))

    assert llm.judge([]) == {}
    assert requests == []


def test_summarize_returns_the_japanese_summary() -> None:
    summary = {"summary_ja": "要約です。", "detail_ja": ["点 1", "点 2"]}
    llm, requests = summarizer(
        lambda _body: httpx2.Response(200, json=message(json.dumps(summary)))
    )

    result = llm.summarize(entry(title="New model"), "x" * (SUMMARY_INPUT_CHARS + 100))

    assert result.summary_ja == "要約です。"
    assert result.detail_ja == ["点 1", "点 2"]
    content = requests[0]["messages"][0]["content"]
    assert "題名: New model" in content
    # 本文は上限で切って渡す。
    assert content.split("本文:\n")[1] == "x" * SUMMARY_INPUT_CHARS
    assert requests[0]["output_config"]["effort"] == "medium"
    assert requests[0]["output_config"]["format"]["type"] == "json_schema"


def test_api_errors_become_llm_errors() -> None:
    llm, _ = summarizer(lambda _body: httpx2.Response(500, json={"type": "error", "error": {}}))

    with pytest.raises(LLMError, match="request failed"):
        llm.summarize(entry(), "body")


def test_an_unparsable_response_becomes_an_llm_error() -> None:
    llm, _ = summarizer(lambda _body: httpx2.Response(200, json=message("not json")))

    with pytest.raises(LLMError, match="did not match"):
        llm.summarize(entry(), "body")


def test_a_refusal_becomes_an_llm_error() -> None:
    llm, _ = summarizer(lambda _body: httpx2.Response(200, json=message("", stop_reason="refusal")))

    with pytest.raises(LLMError, match="refusal"):
        llm.summarize(entry(), "body")
