"""
Tests for model selection in the OpenAI client (indigo-mcp-server#72):
models are read at call time, the large model is gone, each call carries the
lowest reasoning effort its model accepts, and embeddings keep 1536 dims.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

plugin_path = Path(__file__).parent.parent / "MCP Advanced Tools.indigoPlugin/Contents/Server Plugin"
sys.path.insert(0, str(plugin_path))

from mcp_server.common.openai_client import main as client  # noqa: E402
from mcp_server.tools.search_entities import query_parser  # noqa: E402


def test_models_read_at_call_time(monkeypatch):
    monkeypatch.delenv("SMALL_MODEL", raising=False)
    assert client.get_small_model() == client.DEFAULT_SMALL_MODEL == "gpt-6-luna"
    monkeypatch.setenv("SMALL_MODEL", "gpt-5.4-mini")
    assert client.get_small_model() == "gpt-5.4-mini"

    monkeypatch.delenv("OPENAI_EMBEDDING_MODEL", raising=False)
    assert client.get_embedding_model() == "text-embedding-3-large"


def test_large_model_is_gone():
    for name in ("DEFAULT_MODEL", "SMALL_MODEL", "select_optimal_model", "DEFAULT_SUMMARIZATION_MODEL"):
        assert not hasattr(client, name)
    source = (plugin_path / "plugin.py").read_text() + (plugin_path / "PluginConfig.xml").read_text()
    assert "large_model" not in source and "LARGE_MODEL" not in source


def test_embedding_params_keep_index_width(monkeypatch):
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
    assert client.embedding_request_params() == {"model": "text-embedding-3-large", "dimensions": 1536}
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
    assert client.embedding_request_params() == {"model": "text-embedding-ada-002"}


@pytest.mark.parametrize(
    "model,effort",
    [
        ("gpt-6-luna", "none"),
        ("gpt-6.1-sol", "low"),
        ("gpt-6-astra", "low"),
        ("gpt-5.4-mini", "none"),
        ("gpt-5-mini", "minimal"),
        ("o3", "low"),
        ("gpt-4o", None),
    ],
)
def test_low_reasoning_effort(model, effort):
    assert client.low_reasoning_effort(model) == effort


def test_gpt6_tokenizer_and_unknown_limit():
    assert client._get_token_encoder("gpt-6-luna").name == "o200k_base"
    assert client._token_limit("some-future-model") == client.DEFAULT_TOKEN_LIMIT


def _reply(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_perform_completion_requires_model():
    with pytest.raises(ValueError):
        client.perform_completion("hello", model="")


def test_rejected_effort_is_retried_without_it():
    create = Mock(side_effect=[Exception("Unsupported value: 'reasoning_effort' does not support 'none'"),
                               _reply("ok")])
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with patch.object(client, "_get_client", return_value=fake):
        assert client.perform_completion("hi", model="gpt-6-luna", reasoning_effort="none") == "ok"
    assert create.call_args_list[0].kwargs["reasoning_effort"] == "none"
    assert "reasoning_effort" not in create.call_args_list[1].kwargs


def test_expansion_uses_small_model_and_low_effort(monkeypatch):
    monkeypatch.setenv("SMALL_MODEL", "gpt-6-luna")
    query_parser.clear_query_expansion_cache()
    with patch.object(client, "perform_completion", return_value="porch light entryway") as completion:
        expanded = query_parser.QueryParser().expand_query("porch light")
    assert expanded == "porch light entryway"
    kwargs = completion.call_args.kwargs
    assert kwargs["model"] == "gpt-6-luna" and kwargs["reasoning_effort"] == "none"

    # cached per model: a model change asks again
    monkeypatch.setenv("SMALL_MODEL", "gpt-5.4-mini")
    with patch.object(client, "perform_completion", return_value="porch light porch lamp") as completion:
        assert query_parser.QueryParser().expand_query("porch light") == "porch light porch lamp"
    assert completion.call_args.kwargs["model"] == "gpt-5.4-mini"


def test_expansion_prompt_has_no_example_word_lists():
    # Models copied the old prompt's example rooms and synonym lists into
    # every query (indigo-mcp-server#72)
    prompt = query_parser.EXPANSION_PROMPT.lower()
    for copied in ("lounge", "family room", "illumination", "detector", "dimmer", "->"):
        assert copied not in prompt
    assert "never add a room" in prompt
