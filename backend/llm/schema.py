"""
The JSON shape the model must reply with, and its strict check.

REPLY_SCHEMA is also sent to Ollama (its `format` option) so the model is steered towards it, but the server never
trusts that: parse_reply() checks every reply itself. Anything else raises ReplyInvalid, and the member gets a safe
502 that never contains the model's raw text.
"""
import json

STATUSES = ("answered", "insufficient_information", "out_of_scope")
MAX_ANSWER_CHARS = 800  # about 80 words asked for in the prompt, with room to spare

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": list(STATUSES)},
        "answer": {"type": "string", "minLength": 1, "maxLength": MAX_ANSWER_CHARS},
    },
    "required": ["status", "answer"],
    "additionalProperties": False,
}


class ReplyInvalid(Exception):
    """The model's reply broke the schema. The message is a short reason only, never the reply text."""


def parse_reply(text):
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        raise ReplyInvalid("not JSON") from None
    if not isinstance(data, dict):
        raise ReplyInvalid("not an object")
    if set(data) != {"status", "answer"}:
        raise ReplyInvalid("wrong keys")
    if data["status"] not in STATUSES:
        raise ReplyInvalid("unknown status")
    answer = data["answer"]
    if not isinstance(answer, str) or not answer.strip():
        raise ReplyInvalid("empty or non-text answer")
    answer = answer.strip()
    if len(answer) > MAX_ANSWER_CHARS:
        raise ReplyInvalid("answer too long")
    return {"status": data["status"], "answer": answer}
