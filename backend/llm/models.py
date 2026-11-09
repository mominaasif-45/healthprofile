"""
Approved fictional policy documents and their chunks, for the FAQ assistant's retrieval.

The embedding of each chunk is stored as a PostgreSQL array of floats (ArrayField). The corpus is a handful of short
files, so search loads the vectors and compares them with numpy; no vector extension is needed.
"""
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models


class PolicyDocument(models.Model):
    class Source(models.TextChoices):
        SEED = "seed", "Seeded from backend/llm/policies"
        UPLOAD = "upload", "Uploaded by an admin"

    title = models.CharField(max_length=200)
    filename = models.CharField(max_length=255)
    content = models.TextField()
    sha256 = models.CharField(max_length=64)
    size_bytes = models.PositiveIntegerField()
    source = models.CharField(max_length=10, choices=Source.choices)
    # No index: nothing queries documents by uploader (an index needs a query that uses it).
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+", db_index=False)
    embedding_model = models.CharField(max_length=100)  # which embedder made the chunk vectors
    chunk_size = models.PositiveIntegerField()
    chunk_overlap = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["sha256", "embedding_model"], name="policy_document_unique_content"),
        ]

    def __str__(self):
        return self.title


class PolicyChunk(models.Model):
    # No separate index: the unique (document, position) constraint already starts with document_id.
    document = models.ForeignKey(PolicyDocument, on_delete=models.CASCADE, related_name="chunks", db_index=False)
    position = models.PositiveIntegerField()
    start_char = models.PositiveIntegerField()
    end_char = models.PositiveIntegerField()
    text = models.TextField()
    embedding = ArrayField(models.FloatField())

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "position"], name="policy_chunk_unique_position"),
        ]
        ordering = ["document_id", "position"]
