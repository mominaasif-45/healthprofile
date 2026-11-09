"""
ask(question): build the prompt, call the provider with the limits, check the reply against the schema.

Raises ProviderError subclasses or ReplyInvalid; the view turns them into safe errors. Nothing here logs or stores
the question or the answer.
"""
import time

from django.conf import settings

from . import prompts, providers
from .schema import REPLY_SCHEMA, parse_reply

DISCLAIMER = ("Educational demo on synthetic data. General information about the HealthProfile app only: not medical "
              "advice, not a diagnosis, and not a decision about any real person.")
LOCAL_COST = {"amount": "0.00", "currency": "USD",
              "note": "Local model on this computer: no per-token charge. Hardware and electricity are not counted."}


def ask(question):
    provider = providers.get_provider()
    started = time.perf_counter()
    result = provider.complete(prompts.build_messages(question), schema=REPLY_SCHEMA,
                               max_tokens=settings.LLM_MAX_TOKENS, temperature=settings.LLM_TEMPERATURE)
    reply = parse_reply(result.text)
    latency_ms = round((time.perf_counter() - started) * 1000)
    counts = (result.prompt_tokens, result.completion_tokens)
    return {
        **reply,
        "provider": provider.name,
        "model": result.model,
        "prompt_version": prompts.SYSTEM_PROMPT_VERSION,
        "usage": {"prompt_tokens": counts[0], "completion_tokens": counts[1],
                  "total_tokens": None if None in counts else sum(counts), "source": result.token_source},
        "cost": dict(LOCAL_COST),
        "latency_ms": latency_ms,
        "disclaimer": DISCLAIMER,
    }
