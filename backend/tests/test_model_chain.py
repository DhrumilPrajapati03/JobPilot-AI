"""Model fallback across Groq models with separate free-tier quotas."""

import asyncio

import pytest

from app.services import llm
from app.services.llm import ModelChain, ModelsExhausted

RATE_LIMIT = "Error code: 429 - Rate limit reached for model on tokens per day (TPD). Please try again in 7m38.784s."


class Fake:
    def __init__(self, name, fail=None, chunks=("ok",), fail_after=None):
        self.name, self.fail, self.chunks, self.fail_after = name, fail, chunks, fail_after
        self.calls = 0

    async def ainvoke(self, _input, _config=None, **_kw):
        self.calls += 1
        if self.fail:
            raise RuntimeError(self.fail)
        return self.name

    async def astream(self, _input, _config=None, **_kw):
        self.calls += 1
        if self.fail:
            raise RuntimeError(self.fail)
        for i, c in enumerate(self.chunks):
            if self.fail_after is not None and i == self.fail_after:
                raise RuntimeError(RATE_LIMIT)
            yield c

    def bind_tools(self, _tools, **_kw):
        return self


@pytest.fixture(autouse=True)
def clear_cooldowns(monkeypatch):
    monkeypatch.setattr(llm, "_cooldown", {})


def test_falls_back_on_rate_limit_and_remembers_cooldown():
    big, small = Fake("big", fail=RATE_LIMIT), Fake("small")
    chain = ModelChain([big, small], ["big", "small"])
    assert asyncio.run(chain.ainvoke("hi")) == "small"
    assert asyncio.run(chain.ainvoke("hi")) == "small"
    assert big.calls == 1  # skipped while cooling down (7m38s)
    assert 450 < llm._cooldown["big"] - llm.time.monotonic() < 460


def test_other_errors_are_not_swallowed():
    chain = ModelChain([Fake("a", fail="401 invalid api key"), Fake("b")], ["a", "b"])
    with pytest.raises(RuntimeError, match="invalid api key"):
        asyncio.run(chain.ainvoke("hi"))


def test_all_exhausted_gives_a_clear_message():
    chain = ModelChain([Fake("a", fail=RATE_LIMIT), Fake("b", fail="503 over capacity")], ["a", "b"])
    with pytest.raises(ModelsExhausted, match="usage limit") as err:
        asyncio.run(chain.ainvoke("hi"))
    assert "minute" in str(err.value)


def test_stream_falls_back_only_before_output_starts():
    async def collect(chain):
        return [c async for c in chain.astream("hi")]

    chain = ModelChain([Fake("a", fail=RATE_LIMIT), Fake("b", chunks=("he", "llo"))], ["a", "b"])
    assert asyncio.run(collect(chain)) == ["he", "llo"]

    llm._cooldown.clear()
    midway = ModelChain([Fake("a", chunks=("par", "tial"), fail_after=1), Fake("b")], ["a", "b"])
    with pytest.raises(RuntimeError, match="429"):
        asyncio.run(collect(midway))


def test_bound_tools_keep_the_chain():
    chain = ModelChain([Fake("a", fail=RATE_LIMIT), Fake("b")], ["a", "b"]).bind_tools([{"name": "x"}])
    assert isinstance(chain, ModelChain) and asyncio.run(chain.ainvoke("hi")) == "b"


def test_light_tasks_start_with_the_small_model(monkeypatch):
    monkeypatch.setattr(llm.settings, "GROQ_MODEL", "")
    monkeypatch.setattr(llm.settings, "GROQ_LIGHT_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setattr(llm.settings, "GROQ_FALLBACK_MODELS", "openai/gpt-oss-20b,qwen/qwen3.8-27b")
    assert llm.groq_models() == ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
    assert llm.groq_models("light")[0] == "openai/gpt-oss-20b"


def test_assistant_shows_a_friendly_message_when_models_are_exhausted():
    from app.agents import assistant
    from app.services.auth import CurrentUser

    chain = ModelChain([Fake("a", fail=RATE_LIMIT)], ["a"])

    async def run():
        return [e async for e in assistant.run_assistant([{"role": "user", "content": "hi"}], CurrentUser(id="u", token="t"), llm=chain)]

    events = asyncio.run(run())
    error = next(e for e in events if e["type"] == "error")
    assert error["message"].startswith("All the AI models") and "Last error" not in error["message"]
