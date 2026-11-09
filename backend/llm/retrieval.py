"""
Find the policy chunks most similar to a question: cosine similarity with numpy.

Only chunks embedded by the CURRENT embedder are compared (vectors from different models cannot be compared). Chunks
below LLM_MIN_SIMILARITY are dropped, the rest are sorted best first and cut to LLM_TOP_K. `best_score` is the best
similarity before the threshold (None if there was nothing to compare), so a refusal can be explained.
"""
from dataclasses import dataclass, field

import numpy as np
from django.conf import settings

from . import embeddings
from .models import PolicyChunk


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    document_id: int
    document_title: str
    text: str
    score: float


@dataclass(frozen=True)
class Retrieval:
    chunks: list = field(default_factory=list)
    best_score: float | None = None
    embedding_model: str = ""


def _unit(matrix):
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    return np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms > 0)


def retrieve(question):
    embedder = embeddings.get_embedder()
    rows = list(PolicyChunk.objects.filter(document__embedding_model=embedder.model_id)
                .select_related("document").only("id", "text", "embedding", "document__id", "document__title"))
    if not rows:
        return Retrieval(embedding_model=embedder.model_id)
    query = _unit(np.asarray(embedder.embed_query(question), dtype=float))
    matrix = _unit(np.asarray([row.embedding for row in rows], dtype=float))
    scores = matrix @ query
    order = np.argsort(-scores, kind="stable")
    chosen = [i for i in order if scores[i] >= settings.LLM_MIN_SIMILARITY][: settings.LLM_TOP_K]
    chunks = [RetrievedChunk(chunk_id=str(rows[i].id), document_id=rows[i].document.id,
                             document_title=rows[i].document.title, text=rows[i].text, score=round(float(scores[i]), 4))
              for i in chosen]
    return Retrieval(chunks=chunks, best_score=round(float(scores[order[0]]), 4), embedding_model=embedder.model_id)
