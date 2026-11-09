"""
Provider adapter: one small interface, two providers.

* `fake` (the default, used in tests and CI): no network, no model; a valid reply that cites the first document it
  was sent, and estimated tokens.
* `ollama` (only when LLM_PROVIDER=ollama is set in your own .env): a local Ollama server on THIS machine, called with
  Python's built-in urllib. Token counts are Ollama's own (prompt_eval_count, eval_count).

Privacy guards in the Ollama provider: the base URL must point at this machine (localhost / 127.0.0.1 / ::1), and the
HTTP opener ignores HTTP(S)_PROXY settings, so a question can never leave the machine.

Every failure becomes a ProviderError subclass with no raw text in it; the view turns those into safe errors.
"""
import json
import math
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
FAKE_ANSWER = "This is the fake assistant used in tests and CI. No language model was called."
FAKE_DOCUMENT = re.compile(r'<document id="([^"]+)">\n(.*?)\n</document>', re.S)


@dataclass(frozen=True)
class ProviderResult:
    text: str                      # the model's reply, still unchecked
    prompt_tokens: int | None
    completion_tokens: int | None
    model: str
    token_source: str              # "provider" (counted by the model server) or "estimate"


class ProviderError(Exception):
    """Base class. Messages are short fixed reasons, never question or reply text."""


class ProviderUnavailable(ProviderError):
    pass


class ProviderTimeout(ProviderError):
    pass


class ProviderBadReply(ProviderError):
    pass


def estimate_tokens(text):
    """Rough count (about 4 characters per token), used only by the fake provider."""
    return math.ceil(len(text) / 4)


def fake_reply(messages):
    """Cites the first document it was sent (its first 60 characters), so the citation check has real work to do."""
    found = FAKE_DOCUMENT.search(messages[-1]["content"])
    if not found:
        return json.dumps({"status": "insufficient_information", "answer": FAKE_ANSWER, "citations": []})
    chunk_id, text = found.groups()
    return json.dumps({"status": "answered", "answer": FAKE_ANSWER,
                       "citations": [{"chunk_id": chunk_id, "quote": text.strip()[:60].strip()}]})


class FakeProvider:
    name = "fake"

    def complete(self, messages, *, schema, max_tokens, temperature):
        prompt = "".join(message["content"] for message in messages)
        reply = fake_reply(messages)
        return ProviderResult(text=reply, prompt_tokens=estimate_tokens(prompt),
                              completion_tokens=estimate_tokens(reply), model="fake-1", token_source="estimate")


def make_opener():
    """An empty ProxyHandler: urllib would otherwise send requests through HTTP(S)_PROXY from the environment."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _open(request, timeout):
    return make_opener().open(request, timeout=timeout)


def _is_timeout(exc):
    reason = getattr(exc, "reason", None)
    return isinstance(exc, (socket.timeout, TimeoutError)) or isinstance(reason, (socket.timeout, TimeoutError))


def post_json(base_url, path, body, timeout):
    """
    POST JSON to the local Ollama server and return the decoded JSON reply. Used by the chat provider and the
    embedder. The host is checked BEFORE anything is sent; every failure becomes a ProviderError with no text in it.
    """
    base_url = base_url.rstrip("/")
    parts = urllib.parse.urlparse(base_url)
    if parts.scheme not in ("http", "https") or parts.hostname not in LOCAL_HOSTS:
        raise ProviderUnavailable("LLM_BASE_URL must point at this machine")
    request = urllib.request.Request(f"{base_url}{path}", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _open(request, timeout=timeout) as response:
            raw = response.read()
    except Exception as exc:  # noqa: BLE001 - every network failure becomes a safe provider error
        if _is_timeout(exc):
            raise ProviderTimeout("timed out") from None
        raise ProviderUnavailable(type(exc).__name__) from None
    try:
        return json.loads(raw)
    except ValueError:
        raise ProviderBadReply("unexpected response envelope") from None


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url, model, context_tokens, timeout):
        self.base_url, self.model = base_url, model
        self.context_tokens, self.timeout = context_tokens, timeout

    def complete(self, messages, *, schema, max_tokens, temperature):
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": schema,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": self.context_tokens,
                        "seed": 42},
        }
        envelope = post_json(self.base_url, "/api/chat", body, self.timeout)
        try:
            text = envelope["message"]["content"]
            if not isinstance(text, str):
                raise TypeError
        except (KeyError, TypeError):
            raise ProviderBadReply("unexpected response envelope") from None
        return ProviderResult(text=text, prompt_tokens=_count(envelope.get("prompt_eval_count")),
                              completion_tokens=_count(envelope.get("eval_count")),
                              model=str(envelope.get("model") or self.model), token_source="provider")


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def get_provider():
    if settings.LLM_PROVIDER == "fake":
        return FakeProvider()
    if settings.LLM_PROVIDER == "ollama":
        return OllamaProvider(settings.LLM_BASE_URL, settings.LLM_MODEL, settings.LLM_CONTEXT_TOKENS,
                              settings.LLM_TIMEOUT_SECONDS)
    raise ProviderUnavailable("unknown LLM_PROVIDER")
