"""
Embedders: turn text into a vector so similar texts get similar vectors.

* `fake` (default in tests and CI): a deterministic hashing embedder. Each word (minus a few very common ones) adds 1
  to one of 256 slots chosen by its MD5 hash; the vector is scaled to length 1. Texts sharing words are similar. No
  network and no model, so it shows the pipeline works, not real meaning.
* `ollama`: nomic-embed-text on the local Ollama server (POST /api/embed), through the same local-only HTTP helper
  as the chat model. nomic expects task prefixes: "search_document: " for stored chunks, "search_query: " for
  questions.

LLM_EMBEDDER defaults to LLM_PROVIDER, so setting LLM_PROVIDER=ollama in your own .env switches both.
Each document records which embedder made its vectors (`model_id`); retrieval only compares vectors from the same one.
"""
import hashlib
import math
import re

from django.conf import settings

from . import providers

FAKE_DIMENSIONS = 256
STOPWORDS = frozenset("a an and are as at be by can do does for from how i in is it many may me my of on or "
                      "the their there this to was what when where which who will with you your".split())


class FakeEmbedder:
    model_id = f"fake-hash-{FAKE_DIMENSIONS}"

    def _embed(self, text):
        vector = [0.0] * FAKE_DIMENSIONS
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            if word not in STOPWORDS:
                vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % FAKE_DIMENSIONS] += 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm else vector

    def embed_documents(self, texts):
        return [self._embed(text) for text in texts]

    def embed_query(self, text):
        return self._embed(text)


class OllamaEmbedder:
    def __init__(self, base_url, model, timeout):
        self.base_url, self.model, self.timeout = base_url, model, timeout
        self.model_id = f"ollama:{model}"

    def _embed(self, inputs):
        reply = providers.post_json(self.base_url, "/api/embed", {"model": self.model, "input": inputs}, self.timeout)
        vectors = reply.get("embeddings") if isinstance(reply, dict) else None
        if (not isinstance(vectors, list) or len(vectors) != len(inputs)
                or not all(isinstance(v, list) and v and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                                              for x in v) for v in vectors)
                or len({len(v) for v in vectors}) != 1):
            raise providers.ProviderBadReply("unexpected embedding response")
        return [[float(x) for x in v] for v in vectors]

    def embed_documents(self, texts):
        return self._embed([f"search_document: {text}" for text in texts])

    def embed_query(self, text):
        return self._embed([f"search_query: {text}"])[0]


def get_embedder():
    if settings.LLM_EMBEDDER == "fake":
        return FakeEmbedder()
    if settings.LLM_EMBEDDER == "ollama":
        return OllamaEmbedder(settings.LLM_BASE_URL, settings.LLM_EMBED_MODEL, settings.LLM_EMBED_TIMEOUT_SECONDS)
    raise providers.ProviderUnavailable("unknown LLM_EMBEDDER")
