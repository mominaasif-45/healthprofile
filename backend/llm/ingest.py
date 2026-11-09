"""
Store one policy document: chunk it, embed every chunk, then save the document and its chunks in one transaction.

The embeddings are computed BEFORE anything is written, and the writes share one transaction, so a failed embedding
call or a duplicate leaves nothing behind. The same content (SHA-256 of the text) can be stored once per embedder.
"""
import hashlib

from django.conf import settings
from django.db import IntegrityError, transaction

from . import chunking, embeddings
from .models import PolicyChunk, PolicyDocument


class DuplicateDocument(Exception):
    pass


def content_sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ingest_document(*, filename, title, text, source, uploaded_by=None):
    size, overlap = settings.LLM_CHUNK_SIZE, settings.LLM_CHUNK_OVERLAP
    embedder = embeddings.get_embedder()
    sha = content_sha256(text)
    if PolicyDocument.objects.filter(sha256=sha, embedding_model=embedder.model_id).exists():
        raise DuplicateDocument()
    pieces = chunking.chunk_text(text, size=size, overlap=overlap)
    vectors = embedder.embed_documents([piece.text for piece in pieces])
    try:
        with transaction.atomic():
            document = PolicyDocument.objects.create(
                title=title, filename=filename, content=text, sha256=sha, size_bytes=len(text.encode("utf-8")),
                source=source, uploaded_by=uploaded_by, embedding_model=embedder.model_id,
                chunk_size=size, chunk_overlap=overlap,
            )
            PolicyChunk.objects.bulk_create([
                PolicyChunk(document=document, position=i, start_char=piece.start, end_char=piece.end,
                            text=piece.text, embedding=vector)
                for i, (piece, vector) in enumerate(zip(pieces, vectors))
            ])
    except IntegrityError:  # the same content was stored by a parallel request
        raise DuplicateDocument() from None
    return document
