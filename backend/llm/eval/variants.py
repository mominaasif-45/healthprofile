"""
The two system prompts compared by the evaluation. Retrieval settings are the same for both.

* A: the production prompt (llm/prompts.py, faq-system-2), unchanged.
* B: A with ONE line changed: the reply-format line asks for a one-sentence answer that says only what the quote says,
  instead of "plain text, at most 80 words". Only this dimension (how long and how tightly bound to the quote the
  answer is) differs, so a difference in results can be pinned on it, as far as 12 cases allow.

The production endpoint always uses A; B exists only here.
"""
from llm import prompts

A_FORMAT = '"answer": "<plain text, at most 80 words>"'
B_FORMAT = '"answer": "<one sentence that says only what your quote says, nothing more>"'

assert prompts.SYSTEM_PROMPT.count(A_FORMAT) == 1, "prompt A changed: update the evaluation variant"

PROMPTS = {
    "A": {"version": prompts.SYSTEM_PROMPT_VERSION, "text": prompts.SYSTEM_PROMPT,
          "description": "Production prompt: answer in plain text, at most 80 words."},
    "B": {"version": f"{prompts.SYSTEM_PROMPT_VERSION}-b", "text": prompts.SYSTEM_PROMPT.replace(A_FORMAT, B_FORMAT),
          "description": "Same prompt, one line changed: answer in one sentence that says only what the quote says."},
}
CHANGED_LINE = {"A": A_FORMAT, "B": B_FORMAT}
