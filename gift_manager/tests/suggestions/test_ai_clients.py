"""Unit tests for AI provider clients and adapters."""

import json
from unittest import mock

import anthropic
import openai
import pytest

from gift_manager.suggestions.ai.anthropic_client import AnthropicClient
from gift_manager.suggestions.ai.client import AIError
from gift_manager.suggestions.ai.client import get_ai_client
from gift_manager.suggestions.ai.openai_client import OpenAIClient


@pytest.fixture
def dummy_schema():
    return {
        "type": "object",
        "properties": {"ideas": {"type": "array"}},
        "required": ["ideas"],
    }


def test_get_ai_client_disabled_without_provider(settings):
    settings.GIFT_SUGGESTIONS_AI_PROVIDER = ""
    assert get_ai_client() is None


def test_unknown_provider_disables(settings, caplog):
    settings.GIFT_SUGGESTIONS_AI_PROVIDER = "mistral"
    client = get_ai_client()
    assert client is None
    assert "mistral" in caplog.text


def test_anthropic_without_key_disables(settings, caplog):
    settings.GIFT_SUGGESTIONS_AI_PROVIDER = "anthropic"
    settings.GIFT_SUGGESTIONS_AI_API_KEY = ""
    client = get_ai_client()
    assert client is None
    assert "GIFT_SUGGESTIONS_AI_API_KEY" in caplog.text


def test_openai_without_model_disables(settings, caplog):
    settings.GIFT_SUGGESTIONS_AI_PROVIDER = "openai"
    settings.GIFT_SUGGESTIONS_AI_API_KEY = "sk-test-key"
    settings.GIFT_SUGGESTIONS_AI_MODEL = ""
    client = get_ai_client()
    assert client is None
    assert "GIFT_SUGGESTIONS_AI_MODEL" in caplog.text


def test_openai_without_key_and_without_base_url_disables(settings, caplog):
    settings.GIFT_SUGGESTIONS_AI_PROVIDER = "openai"
    settings.GIFT_SUGGESTIONS_AI_API_KEY = ""
    settings.GIFT_SUGGESTIONS_AI_BASE_URL = ""
    settings.GIFT_SUGGESTIONS_AI_MODEL = "gpt-4o"
    client = get_ai_client()
    assert client is None
    assert "GIFT_SUGGESTIONS_AI_API_KEY" in caplog.text


def test_openai_base_url_allows_missing_key(settings):
    settings.GIFT_SUGGESTIONS_AI_PROVIDER = "openai"
    settings.GIFT_SUGGESTIONS_AI_API_KEY = ""
    settings.GIFT_SUGGESTIONS_AI_BASE_URL = "http://localhost:8000/v1"
    settings.GIFT_SUGGESTIONS_AI_MODEL = "gpt-4o"
    client = get_ai_client()
    assert isinstance(client, OpenAIClient)
    assert client.model == "gpt-4o"
    assert client.base_url == "http://localhost:8000/v1"


def test_anthropic_default_model_is_haiku(settings):
    settings.GIFT_SUGGESTIONS_AI_PROVIDER = "anthropic"
    settings.GIFT_SUGGESTIONS_AI_API_KEY = "sk-ant-test"
    settings.GIFT_SUGGESTIONS_AI_MODEL = ""
    client = get_ai_client()
    assert isinstance(client, AnthropicClient)
    assert client.model == "claude-haiku-5-5"


@mock.patch("anthropic.Anthropic")
def test_anthropic_request_shape(mock_anthropic_cls, dummy_schema):
    mock_instance = mock.MagicMock()
    mock_anthropic_cls.return_value = mock_instance

    mock_resp = mock.MagicMock()
    mock_resp.stop_reason = "end_turn"
    mock_block = mock.MagicMock()
    mock_block.type = "text"
    mock_block.text = '{"ideas": []}'
    mock_resp.content = [mock_block]
    mock_instance.messages.create.return_value = mock_resp

    client = AnthropicClient(
        api_key="sk-ant-secret",
        model="claude-haiku-5-5",
        timeout=20.0,
        effort="low",
    )
    mock_anthropic_cls.assert_called_once_with(api_key="sk-ant-secret", timeout=20.0, max_retries=0)

    payload = {"zebra": 1, "apple": 2}
    result = client.generate(system="Be helpful", payload=payload, schema=dummy_schema)

    assert result == '{"ideas": []}'
    mock_instance.messages.create.assert_called_once_with(
        model="claude-haiku-5-5",
        max_tokens=4096,
        system="Be helpful",
        messages=[
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            }
        ],
        output_config={
            "format": {"type": "json_schema", "schema": dummy_schema},
            "effort": "low",
        },
    )


@mock.patch("anthropic.Anthropic")
def test_anthropic_request_shape_omits_effort_when_empty(mock_anthropic_cls, dummy_schema):
    mock_instance = mock.MagicMock()
    mock_anthropic_cls.return_value = mock_instance

    mock_resp = mock.MagicMock()
    mock_resp.stop_reason = "end_turn"
    mock_resp.content = [mock.MagicMock(type="text", text="{}")]
    mock_instance.messages.create.return_value = mock_resp

    client = AnthropicClient(
        api_key="sk-ant-secret",
        model="claude-haiku-5-5",
        timeout=15.0,
        effort="",
    )
    client.generate(system="sys", payload={"a": 1}, schema=dummy_schema)

    _, kwargs = mock_instance.messages.create.call_args
    assert kwargs["output_config"] == {"format": {"type": "json_schema", "schema": dummy_schema}}


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
@mock.patch("anthropic.Anthropic")
def test_anthropic_refusal_and_max_tokens_raise_ai_error(
    mock_anthropic_cls, stop_reason, dummy_schema
):
    mock_instance = mock.MagicMock()
    mock_anthropic_cls.return_value = mock_instance

    mock_resp = mock.MagicMock()
    mock_resp.stop_reason = stop_reason
    mock_resp.content = [mock.MagicMock(type="text", text="incomplete")]
    mock_instance.messages.create.return_value = mock_resp

    client = AnthropicClient(
        api_key="sk-ant",
        model="claude-haiku-5-5",
        timeout=15.0,
        effort="low",
    )
    with pytest.raises(AIError, match=stop_reason):
        client.generate(system="sys", payload={}, schema=dummy_schema)


@pytest.mark.parametrize(
    "exc_factory",
    [
        lambda: anthropic.RateLimitError(
            "rate limit",
            response=mock.MagicMock(status_code=429, headers={}, request=mock.MagicMock()),
            body=None,
        ),
        lambda: anthropic.APIStatusError(
            "server error",
            response=mock.MagicMock(status_code=500, headers={}, request=mock.MagicMock()),
            body=None,
        ),
        lambda: anthropic.APIConnectionError(request=mock.MagicMock()),
    ],
)
@mock.patch("anthropic.Anthropic")
def test_anthropic_api_errors_become_ai_error(mock_anthropic_cls, exc_factory, dummy_schema):
    mock_instance = mock.MagicMock()
    mock_anthropic_cls.return_value = mock_instance
    mock_instance.messages.create.side_effect = exc_factory()

    client = AnthropicClient(
        api_key="sk-ant",
        model="claude-haiku-5-5",
        timeout=15.0,
        effort="low",
    )
    with pytest.raises(AIError):
        client.generate(system="sys", payload={}, schema=dummy_schema)


@mock.patch("openai.OpenAI")
def test_openai_request_shape(mock_openai_cls, dummy_schema):
    mock_instance = mock.MagicMock()
    mock_openai_cls.return_value = mock_instance

    mock_choice = mock.MagicMock()
    mock_choice.finish_reason = "stop"
    mock_choice.message.refusal = None
    mock_choice.message.content = '{"ideas": []}'
    mock_resp = mock.MagicMock(choices=[mock_choice])
    mock_instance.chat.completions.create.return_value = mock_resp

    client = OpenAIClient(
        api_key="sk-openai-secret",
        model="gpt-4o-mini",
        base_url="https://api.openai.com/v1",
        timeout=25.0,
    )
    mock_openai_cls.assert_called_once_with(
        api_key="sk-openai-secret",
        base_url="https://api.openai.com/v1",
        timeout=25.0,
        max_retries=0,
    )

    payload = {"beta": 2, "alpha": 1}
    result = client.generate(system="Be concise", payload=payload, schema=dummy_schema)

    assert result == '{"ideas": []}'
    mock_instance.chat.completions.create.assert_called_once_with(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Be concise"},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "gift_ideas",
                "schema": dummy_schema,
                "strict": True,
            },
        },
    )


@pytest.mark.parametrize(
    "finish_reason,refusal",
    [
        ("length", None),
        ("content_filter", None),
        ("stop", "I cannot fulfill this request"),
    ],
)
@mock.patch("openai.OpenAI")
def test_openai_refusal_raises(mock_openai_cls, finish_reason, refusal, dummy_schema):
    mock_instance = mock.MagicMock()
    mock_openai_cls.return_value = mock_instance

    mock_choice = mock.MagicMock()
    mock_choice.finish_reason = finish_reason
    mock_choice.message.refusal = refusal
    mock_choice.message.content = "incomplete"
    mock_instance.chat.completions.create.return_value = mock.MagicMock(choices=[mock_choice])

    client = OpenAIClient(
        api_key="sk-test",
        model="gpt-4o-mini",
        base_url=None,
        timeout=15.0,
    )
    with pytest.raises(AIError):
        client.generate(system="sys", payload={}, schema=dummy_schema)


@pytest.mark.parametrize(
    "exc_factory",
    [
        lambda: openai.RateLimitError(
            "rate limit",
            response=mock.MagicMock(status_code=429, headers={}, request=mock.MagicMock()),
            body=None,
        ),
        lambda: openai.APIStatusError(
            "server error",
            response=mock.MagicMock(status_code=500, headers={}, request=mock.MagicMock()),
            body=None,
        ),
        lambda: openai.APIConnectionError(request=mock.MagicMock()),
    ],
)
@mock.patch("openai.OpenAI")
def test_openai_api_errors_become_ai_error(mock_openai_cls, exc_factory, dummy_schema):
    mock_instance = mock.MagicMock()
    mock_openai_cls.return_value = mock_instance
    mock_instance.chat.completions.create.side_effect = exc_factory()

    client = OpenAIClient(
        api_key="sk-test",
        model="gpt-4o-mini",
        base_url=None,
        timeout=15.0,
    )
    with pytest.raises(AIError):
        client.generate(system="sys", payload={}, schema=dummy_schema)


@mock.patch("anthropic.Anthropic")
@mock.patch("openai.OpenAI")
def test_api_key_never_logged(mock_openai_cls, mock_anthropic_cls, caplog, dummy_schema):
    anthropic_key = "sk-ant-very-secret-token-12345"
    openai_key = "sk-openai-very-secret-token-67890"

    mock_ant_instance = mock.MagicMock()
    mock_anthropic_cls.return_value = mock_ant_instance
    mock_ant_instance.messages.create.side_effect = anthropic.APIStatusError(
        f"Error with key {anthropic_key}",
        response=mock.MagicMock(status_code=401, headers={}, request=mock.MagicMock()),
        body=None,
    )

    mock_oa_instance = mock.MagicMock()
    mock_openai_cls.return_value = mock_oa_instance
    mock_oa_instance.chat.completions.create.side_effect = openai.APIStatusError(
        f"Error with key {openai_key}",
        response=mock.MagicMock(status_code=401, headers={}, request=mock.MagicMock()),
        body=None,
    )

    ant_client = AnthropicClient(api_key=anthropic_key, model="claude-haiku-5-5", timeout=15.0)
    with pytest.raises(AIError):
        ant_client.generate(system="sys", payload={}, schema=dummy_schema)

    oa_client = OpenAIClient(api_key=openai_key, model="gpt-4o-mini", base_url="", timeout=15.0)
    with pytest.raises(AIError):
        oa_client.generate(system="sys", payload={}, schema=dummy_schema)

    assert anthropic_key not in caplog.text
    assert openai_key not in caplog.text
