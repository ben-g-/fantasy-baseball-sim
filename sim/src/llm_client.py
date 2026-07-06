"""Provider-agnostic LLM client wrapper.

This is the only module in the codebase that imports a provider SDK or
knows a provider-specific request shape. Every caller sees a single
function — text in, text out. Switching providers or models means
changing this module's implementation and MODEL_ID; no other module
needs to change.
"""

import os

import anthropic

MODEL_ID = 'claude-sonnet-5'

_client: anthropic.Anthropic | None = None


class RecapRefusedError(Exception):
    """Raised when the model declines to generate a response."""


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    return _client


def generate_text(prompt: str, max_tokens: int = 1024) -> str:
    """Send a single-turn text prompt and return the model's text response."""
    response = _get_client().messages.create(
        model=MODEL_ID,
        max_tokens=max_tokens,
        messages=[{'role': 'user', 'content': prompt}],
    )
    if response.stop_reason == 'refusal':
        raise RecapRefusedError('LLM declined to generate a response')
    return ''.join(block.text for block in response.content if block.type == 'text')
