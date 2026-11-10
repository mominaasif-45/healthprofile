"""Shared helpers for the LLM tests (kept out of conftest.py, which is frozen Week 1-3 code)."""
import importlib
import json
import re

EMERGENCY_POLICY = (
    "# Emergency contacts\n\n"
    "A member can add up to three emergency contacts to a profile. Exactly one of them is the primary contact.\n"
)
REMINDER_POLICY = (
    "# Appointment reminders\n\n"
    "The demo clinic sends one reminder message two days before each fictional appointment.\n"
)
DOCUMENT = re.compile(r'<document id="([^"]+)">\n(.*?)\n</document>', re.S)


def llm(name):
    """Imported inside tests, so that before phase 3/4 existed the tests failed instead of stopping at import."""
    return importlib.import_module(f"llm.{name}")


def sent_documents(messages):
    """[(chunk_id, text)] for every <document> block in the user message."""
    return DOCUMENT.findall(messages[-1]["content"])


def citing_reply(messages, answer="Up to three emergency contacts can be added."):
    """A valid reply that cites the first document sent, quoting its first 60 characters."""
    docs = sent_documents(messages)
    if not docs:
        return json.dumps({"status": "insufficient_information", "answer": "Not in the documents.", "citations": []})
    chunk_id, text = docs[0]
    return json.dumps({"status": "answered", "answer": answer,
                       "citations": [{"chunk_id": chunk_id, "quote": text.strip()[:60].strip()}]})


def add_policy(text=EMERGENCY_POLICY, filename="emergency-contacts.md", source="seed", uploaded_by=None):
    ingest = llm("ingest")
    extracted = llm("extract").extract_text(filename, text.encode("utf-8"))
    return ingest.ingest_document(filename=filename, title=extracted.title, text=extracted.text, source=source,
                                  uploaded_by=uploaded_by)


def rag_settings(settings):
    """Fixed retrieval settings for tests: fake embedder and provider, a low threshold for the hashing embedder."""
    settings.LLM_PROVIDER = "fake"
    settings.LLM_EMBEDDER = "fake"
    settings.LLM_CHUNK_SIZE = 600
    settings.LLM_CHUNK_OVERLAP = 100
    settings.LLM_TOP_K = 3
    settings.LLM_MIN_SIMILARITY = 0.1
