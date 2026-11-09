"""
The JSON shape the model must reply with, and its strict check.

REPLY_SCHEMA is also sent to Ollama (its `format` option) so the model is steered towards it, but the server never
trusts that: parse_reply() checks every reply itself. Anything else raises ReplyInvalid, and the member gets a safe
502 that never contains the model's raw text. Whether each citation is TRUE is checked later (service.py).
"""
import json

STATUSES = ("answered", "insufficient_information", "out_of_scope")
MAX_ANSWER_CHARS = 800  # about 80 words asked for in the prompt, with room to spare
MAX_CITATIONS = 3
MAX_QUOTE_CHARS = 300

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": list(STATUSES)},
        "answer": {"type": "string", "minLength": 1, "maxLength": MAX_ANSWER_CHARS},
        "citations": {
            "type": "array",
            "maxItems": MAX_CITATIONS,
            "items": {
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string"},
                    "quote": {"type": "string", "minLength": 1, "maxLength": MAX_QUOTE_CHARS},
                },
                "required": ["chunk_id", "quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["status", "answer", "citations"],
    "additionalProperties": False,
}


class ReplyInvalid(Exception):
    """The model's reply broke the schema. The message is a short reason only, never the reply text."""


def _citation(item):
    if not isinstance(item, dict) or set(item) != {"chunk_id", "quote"}:
        raise ReplyInvalid("citation has wrong keys")
    chunk_id, quote = item["chunk_id"], item["quote"]
    if not isinstance(chunk_id, str) or not isinstance(quote, str):
        raise ReplyInvalid("citation is not text")
    if not quote.strip() or len(quote) > MAX_QUOTE_CHARS:
        raise ReplyInvalid("citation quote empty or too long")
    return {"chunk_id": chunk_id.strip(), "quote": quote.strip()}


def parse_reply(text):
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        raise ReplyInvalid("not JSON") from None
    if not isinstance(data, dict):
        raise ReplyInvalid("not an object")
    if set(data) != {"status", "answer", "citations"}:
        raise ReplyInvalid("wrong keys")
    if data["status"] not in STATUSES:
        raise ReplyInvalid("unknown status")
    answer = data["answer"]
    if not isinstance(answer, str) or not answer.strip():
        raise ReplyInvalid("empty or non-text answer")
    answer = answer.strip()
    if len(answer) > MAX_ANSWER_CHARS:
        raise ReplyInvalid("answer too long")
    citations = data["citations"]
    if not isinstance(citations, list) or len(citations) > MAX_CITATIONS:
        raise ReplyInvalid("citations not a short list")
    return {"status": data["status"], "answer": answer, "citations": [_citation(item) for item in citations]}
