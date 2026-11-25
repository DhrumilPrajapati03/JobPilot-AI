"""Provider layer contracts (openai SDK against OpenAI-compatible APIs), HTTP mocked."""
import asyncio
import json

import httpx
import pytest

from app.services import llm


def sse(*events) -> bytes:
    return b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events) + b"data: [DONE]\n\n"


def chunk(delta, finish=None):
    return {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": "m",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


def test_stream_merges_text_and_split_tool_call_arguments(monkeypatch):
    monkeypatch.setattr(llm.settings, "GROQ_API_KEY", "synthetic-test-key")
    seen = []

    def respond(request):
        seen.append(json.loads(request.content))
        body = sse(
            chunk({"role": "assistant", "content": "Looking"}),
            chunk({"content": " now"}),
            chunk({"tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                                   "function": {"name": "list_applications", "arguments": "{\"sta"}}]}),
            chunk({"tool_calls": [{"index": 0, "function": {"arguments": "tus\": \"applied\"}"}}]}),
            chunk({}, finish="tool_calls"),
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    model = llm.ChatModel("groq", "openai/gpt-oss-120b", max_retries=0, http_async_client=client).bind_tools(
        [{"type": "function", "function": {"name": "list_applications", "parameters": {"type": "object", "properties": {}}}}])

    async def run():
        full = None
        async for piece in model.astream([llm.SystemMessage("s"), llm.HumanMessage("hi")]):
            full = piece if full is None else full + piece
        await client.aclose()
        return full

    full = asyncio.run(run())
    assert full.content == "Looking now"
    assert full.tool_calls == [{"name": "list_applications", "args": {"status": "applied"}, "id": "call_1"}]
    assert seen[0]["stream"] is True and seen[0]["tools"][0]["function"]["name"] == "list_applications"
    assert [m["role"] for m in seen[0]["messages"]] == ["system", "user"]


def test_messages_round_trip_tool_calls_and_tool_results():
    out = llm.to_openai_messages([
        llm.SystemMessage("rules"), ("human", "hi"),
        llm.AIMessage(content="", tool_calls=[{"name": "f", "args": {"a": 1}, "id": "t1"}]),
        llm.ToolMessage(content="{\"ok\": true}", tool_call_id="t1"),
    ])
    assert out[0] == {"role": "system", "content": "rules"} and out[1] == {"role": "user", "content": "hi"}
    assert out[2]["tool_calls"][0]["function"] == {"name": "f", "arguments": "{\"a\": 1}"} and out[2]["content"] is None
    assert out[3] == {"role": "tool", "tool_call_id": "t1", "content": "{\"ok\": true}"}


def test_ollama_chat_uses_local_v1_endpoint_and_strips_thinking(monkeypatch):
    monkeypatch.setattr(llm.settings, "OLLAMA_BASE_URL", "http://ollama.invalid:11434/")
    urls = []

    def respond(request):
        urls.append(str(request.url))
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 1, "model": "qwen3:8b",
                                         "choices": [{"index": 0, "finish_reason": "stop",
                                                      "message": {"role": "assistant", "content": "<think>plan</think>\nDone."}}]})

    model = llm.ChatModel("ollama", "qwen3:8b", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    assert model.invoke("hello").content == "Done."
    assert urls == ["http://ollama.invalid:11434/v1/chat/completions"]


def test_ollama_embeddings(monkeypatch):
    def respond(request):
        body = json.loads(request.content)
        assert request.url.path == "/api/embed" and body["model"] == "embeddinggemma"
        return httpx.Response(200, json={"embeddings": [[0.1] * 768 for _ in body["input"]]})

    emb = llm.OllamaEmbeddings(base_url="http://ollama.invalid:11434", client=httpx.Client(transport=httpx.MockTransport(respond)))
    vectors = emb.embed_documents(["a", "b"])
    assert len(vectors) == 2 and len(vectors[0]) == 768
    assert len(emb.embed_query("c")) == 768


@pytest.mark.parametrize("setting,key,expected", [
    ("auto", "real-key", "groq"), ("auto", "", "ollama"), ("auto", "your-groq-api-key", "ollama"),
    ("ollama", "real-key", "ollama"), ("groq", "", "groq"),
])
def test_default_provider(monkeypatch, setting, key, expected):
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", setting)
    monkeypatch.setattr(llm.settings, "GROQ_API_KEY", key)
    assert llm.default_provider() == expected


def test_groq_without_key_is_an_explicit_error(monkeypatch):
    monkeypatch.setattr(llm.settings, "GROQ_API_KEY", "")
    with pytest.raises(ValueError):
        llm.ChatModel("groq", "openai/gpt-oss-120b")
    with pytest.raises(ValueError):
        llm.ChatModel("anthropic", "anything")
