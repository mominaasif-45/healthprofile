"""
ask(question): retrieve policy chunks, call the model with the limits, check the reply, verify every citation.

1. Retrieve the top chunks above the minimum similarity. None -> "insufficient_information" WITHOUT calling the model.
2. Send the chunks (untrusted, in <document> tags in the user message) and the question (as JSON) to the model.
3. parse_reply(): the strict JSON shape, or ReplyInvalid (the view turns it into a safe 502).
4. Verify each citation: its chunk_id must be one that was SENT, and its quote (whitespace, letter case and Markdown
   marks ignored, at least MIN_QUOTE_CHARS) must appear in that chunk as sent, and not in another document that
   was sent (that is boilerplate, such as the shared disclaimer line). Unverified citations are removed.
5. Only "answered" with at least one verified citation, and no copy of the system prompt in the answer, returns the
   model's words. Otherwise the member gets a fixed text: "insufficient_information" (or "out_of_scope"), so the
   model's unsupported words are never shown.

Raises ProviderError subclasses or ReplyInvalid. Nothing here logs or stores the question or the answer.
"""
import re
import time

from django.conf import settings

from . import prompts, providers, retrieval
from .schema import REPLY_SCHEMA, parse_reply

DISCLAIMER = ("Educational demo on synthetic data. Answers come only from fictional HealthProfile demo policies: not "
              "medical advice, not a diagnosis, and not a decision about any real person.")
LOCAL_COST = {"amount": "0.00", "currency": "USD",
              "note": "Local model on this computer: no per-token charge. Hardware and electricity are not counted."}
INSUFFICIENT_ANSWER = ("I could not find this in the approved HealthProfile demo policies, so I will not guess. "
                       "Try rephrasing, or ask about a topic the policies cover.")
OUT_OF_SCOPE_ANSWER = ("This assistant only answers questions about the HealthProfile demo policies. It cannot give "
                       "medical advice; for health questions, please ask a qualified professional.")
MIN_QUOTE_CHARS = 12
LEAK_LINE_CHARS = 25  # a system-prompt sentence at least this long, found in an answer, counts as a leak


def normalise(text):
    """Lower case, Markdown marks (* _ ` #) removed, runs of whitespace collapsed: for comparing quotes."""
    return re.sub(r"\s+", " ", re.sub(r"[*_`#]", "", text)).strip().casefold()


def verify_citations(citations, sent):
    """
    sent: {chunk_id: (document_id, text as sent)}. Returns (verified citations, number removed).

    A quote that appears in chunks of two or more DIFFERENT documents is boilerplate (for example the disclaimer line
    every policy starts with), not evidence for an answer, so it is removed too. Overlapping chunks of one document
    may repeat a quote; that still counts.
    """
    texts = {chunk_id: (document_id, normalise(text)) for chunk_id, (document_id, text) in sent.items()}
    verified, seen = [], set()
    for citation in citations:
        found = texts.get(citation["chunk_id"])
        quote = normalise(citation["quote"]).strip(" \"'“”‘’.,;:")
        key = (citation["chunk_id"], quote)
        if found is None or len(quote) < MIN_QUOTE_CHARS or quote not in found[1] or key in seen:
            continue
        documents_with_quote = {document_id for document_id, text in texts.values() if quote in text}
        if len(documents_with_quote) > 1:
            continue
        seen.add(key)
        verified.append(citation)
    return verified, len(citations) - len(verified)


def _leak_lines(system_prompt):
    pieces = re.split(r"\n|(?<=\.) ", system_prompt)
    return [normalise(piece) for piece in pieces if len(normalise(piece)) >= LEAK_LINE_CHARS]


def leaks_system_prompt(answer, system_prompt=prompts.SYSTEM_PROMPT):
    answer = normalise(answer)
    return any(line in answer for line in _leak_lines(system_prompt))


def ask(question, *, system_prompt=prompts.SYSTEM_PROMPT, prompt_version=prompts.SYSTEM_PROMPT_VERSION):
    """The endpoint always uses the defaults; only the evaluation (llm/eval) passes another system prompt."""
    started = time.perf_counter()
    found = retrieval.retrieve(question)
    info = {
        "top_k": settings.LLM_TOP_K, "min_similarity": settings.LLM_MIN_SIMILARITY,
        "chunk_size": settings.LLM_CHUNK_SIZE, "chunk_overlap": settings.LLM_CHUNK_OVERLAP,
        "embedding_model": found.embedding_model, "best_similarity": found.best_score,
        "chunks_sent": len(found.chunks), "unverified_citations_removed": 0,
    }
    if not found.chunks:
        return _response("insufficient_information", INSUFFICIENT_ANSWER, [], info, None, None, (0, 0, "none"),
                         started, prompt_version)

    provider = providers.get_provider()
    result = provider.complete(prompts.build_messages(question, found.chunks, system_prompt), schema=REPLY_SCHEMA,
                               max_tokens=settings.LLM_MAX_TOKENS, temperature=settings.LLM_TEMPERATURE)
    reply = parse_reply(result.text)
    sent = {chunk.chunk_id: (chunk.document_id, prompts.neutralise(chunk.text)) for chunk in found.chunks}
    verified, removed = verify_citations(reply["citations"], sent)
    info["unverified_citations_removed"] = removed
    usage = (result.prompt_tokens, result.completion_tokens, result.token_source)

    common = (info, provider.name, result.model, usage, started, prompt_version)
    if reply["status"] == "answered" and verified and not leaks_system_prompt(reply["answer"], system_prompt):
        by_id = {chunk.chunk_id: chunk for chunk in found.chunks}
        citations = [{"chunk_id": c["chunk_id"], "document_id": by_id[c["chunk_id"]].document_id,
                      "document_title": by_id[c["chunk_id"]].document_title, "quote": c["quote"]} for c in verified]
        return _response("answered", reply["answer"], citations, *common)
    if reply["status"] == "out_of_scope":
        return _response("out_of_scope", OUT_OF_SCOPE_ANSWER, [], *common)
    return _response("insufficient_information", INSUFFICIENT_ANSWER, [], *common)


def _response(status, answer, citations, info, provider_name, model, usage, started, prompt_version):
    prompt_tokens, completion_tokens, source = usage
    total = None if None in (prompt_tokens, completion_tokens) else prompt_tokens + completion_tokens
    return {
        "status": status,
        "answer": answer,
        "citations": citations,
        "retrieval": info,
        "provider": provider_name or "none",
        "model": model or "none",
        "prompt_version": prompt_version,
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": total,
                  "source": source},
        "cost": dict(LOCAL_COST),
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "disclaimer": DISCLAIMER,
    }
