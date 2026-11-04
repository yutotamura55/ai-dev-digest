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


def articles_in(request: dict[str, Any]) -> Any:
    """リクエストの本文から、<articles> で囲んだ JSON を取り出す。"""
    content = request["messages"][0]["content"]
    return json.loads(content.split("<articles>\n")[1].split("\n</articles>")[0])


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
    # 記事は JSON のデータとして <articles> の中に渡し、指示には信頼しないことを書く。
    assert articles_in(requests[0]) == [
        {"index": 0, "source": "Example", "title": "New model", "excerpt": ""},
        {"index": 1, "source": "Example", "title": "Event", "excerpt": ""},
    ]
    assert "信頼できないデータ" in requests[0]["system"]


def test_judge_ignores_an_index_outside_the_batch() -> None:
    judged = {"items": [{"index": 5, "relevant": True, "score": 80}]}
    llm, _ = summarizer(lambda _body: httpx2.Response(200, json=message(json.dumps(judged))))

    assert llm.judge([entry()]) == {}


def test_judge_splits_many_entries_into_batches() -> None:
    def respond(body: dict[str, Any]) -> httpx2.Response:
        count = len(articles_in(body))
        items = [{"index": i, "relevant": True, "score": 1} for i in range(count)]
        return httpx2.Response(200, json=message(json.dumps({"items": items})))

    llm, requests = summarizer(respond)
    entries = [entry(url=f"https://example.com/{i}") for i in range(JUDGE_BATCH_SIZE + 1)]

    assert len(llm.judge(entries)) == JUDGE_BATCH_SIZE + 1
    assert len(requests) == 2


def test_judge_keeps_the_batches_that_succeeded_when_one_fails() -> None:
    calls = 0

    def respond(body: dict[str, Any]) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx2.Response(500, json={"type": "error", "error": {}})
        count = len(articles_in(body))
        items = [{"index": i, "relevant": True, "score": 1} for i in range(count)]
        return httpx2.Response(200, json=message(json.dumps({"items": items})))

    llm, _ = summarizer(respond)
    entries = [entry(url=f"https://example.com/{i}") for i in range(JUDGE_BATCH_SIZE + 1)]

    # 1 つ目のバッチ (40 件) は失敗し、2 つ目 (1 件) だけが結果に残る。
    assert llm.judge(entries) == {f"https://example.com/{JUDGE_BATCH_SIZE}": 1}


def test_judge_returns_nothing_for_no_entries() -> None:
    llm, requests = summarizer(lambda _body: httpx2.Response(500))

    assert llm.judge([]) == {}
    assert requests == []


def test_summarize_returns_the_japanese_summary() -> None:
    summary = {
        "title_ja": "新しいモデル",
        "summary_ja": "要約です。",
        "detail_ja": ["点 1", "点 2"],
    }
    llm, requests = summarizer(
        lambda _body: httpx2.Response(200, json=message(json.dumps(summary)))
    )

    result = llm.summarize(entry(title="New model"), "x" * (SUMMARY_INPUT_CHARS + 100))

    assert result.title_ja == "新しいモデル"
    assert result.summary_ja == "要約です。"
    assert result.detail_ja == ["点 1", "点 2"]
    [record] = articles_in(requests[0])
    assert record["title"] == "New model"
    assert record["published_at"] == "2026-11-04T01:00:00+00:00"
    # 本文は上限で切って渡す。
    assert record["body"] == "x" * SUMMARY_INPUT_CHARS
    assert "信頼できないデータ" in requests[0]["system"]
    assert "title_ja" in requests[0]["system"]
    assert requests[0]["output_config"]["effort"] == "medium"
    assert "title_ja" in requests[0]["output_config"]["format"]["schema"]["required"]
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
