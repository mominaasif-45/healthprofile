"""
Split text into overlapping chunks of at most `size` characters.

Each chunk tries to end at a natural break (a blank line, then a line end, then a sentence end, then a space) in its
second half, so sentences are cut less often. The next chunk starts `overlap` characters before the previous end (moved
forward to the start of a word), so a sentence cut at a boundary still appears whole in one of the two chunks.
Size and overlap come from settings (LLM_CHUNK_SIZE, LLM_CHUNK_OVERLAP) so phase 5 can compare two settings.
"""
from dataclasses import dataclass

BREAKS = ("\n\n", "\n", ". ", "? ", "! ", " ")


@dataclass(frozen=True)
class Chunk:
    start: int
    end: int
    text: str


def chunk_text(text, size, overlap):
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("chunk size must be positive and overlap must be between 0 and size - 1")
    chunks, start, length = [], 0, len(text)
    while start < length:
        end = min(start + size, length)
        if end < length:
            window = text[start:end]
            for mark in BREAKS:
                cut = window.rfind(mark, size // 2)
                if cut != -1:
                    end = start + cut + len(mark)
                    break
        piece = text[start:end].strip()
        if piece:
            chunks.append(Chunk(start=start, end=end, text=piece))
        if end >= length:
            break
        next_start = max(end - overlap, start + 1)
        while next_start < end and not text[next_start - 1].isspace():  # start at the beginning of a word
            next_start += 1
        start = next_start
    return chunks
