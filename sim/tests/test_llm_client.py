"""Tests for the provider-agnostic LLM client wrapper."""

from types import SimpleNamespace

import pytest

import llm_client


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.captured_kwargs = None

    def create(self, **kwargs):
        self.captured_kwargs = kwargs
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


def _text_response(text: str, stop_reason: str = 'end_turn'):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type='text', text=text)],
    )


def test_generate_text_returns_concatenated_text_blocks(monkeypatch):
    response = SimpleNamespace(
        stop_reason='end_turn',
        content=[
            SimpleNamespace(type='text', text='Hello '),
            SimpleNamespace(type='text', text='world'),
        ],
    )
    fake_client = _FakeClient(response)
    monkeypatch.setattr(llm_client, '_get_client', lambda: fake_client)

    result = llm_client.generate_text('some prompt')

    assert result == 'Hello world', (
        "multiple text content blocks should be concatenated into a single string, "
        "since the wrapper's contract is a single text-out value"
    )


def test_generate_text_sends_prompt_as_single_user_message(monkeypatch):
    fake_client = _FakeClient(_text_response('recap text'))
    monkeypatch.setattr(llm_client, '_get_client', lambda: fake_client)

    llm_client.generate_text('a fully-built prompt')

    kwargs = fake_client.messages.captured_kwargs
    assert kwargs['model'] == llm_client.MODEL_ID, (
        "the wrapper should call the model named by its own MODEL_ID constant, so tests catch "
        "any drift between the constant and the actual call"
    )
    assert kwargs['messages'] == [{'role': 'user', 'content': 'a fully-built prompt'}], (
        "the call shape must be a plain single-turn text completion (no tools, no system "
        "prompt, no extended thinking) so it stays portable across providers"
    )


def test_generate_text_ignores_non_text_content_blocks(monkeypatch):
    response = SimpleNamespace(
        stop_reason='end_turn',
        content=[
            SimpleNamespace(type='thinking', thinking='reasoning...'),
            SimpleNamespace(type='text', text='the actual recap'),
        ],
    )
    fake_client = _FakeClient(response)
    monkeypatch.setattr(llm_client, '_get_client', lambda: fake_client)

    result = llm_client.generate_text('prompt')

    assert result == 'the actual recap', (
        "non-text blocks (e.g. thinking) must not leak into the returned string, since callers "
        "expect plain recap prose"
    )


def test_generate_text_raises_on_refusal(monkeypatch):
    fake_client = _FakeClient(_text_response('', stop_reason='refusal'))
    monkeypatch.setattr(llm_client, '_get_client', lambda: fake_client)

    with pytest.raises(llm_client.RecapRefusedError):
        llm_client.generate_text('prompt')
