"""
Turn an uploaded policy file into plain text, or refuse it with a short fixed message.

Rules: the name must end in .txt or .md (any letter case, and the extension is the LAST one, so "x.md.exe" is
refused); at most 200 KB; valid UTF-8 (a leading byte-order mark is dropped); no NUL bytes (a sign of a binary file);
not empty. The browser's content type is ignored: it is chosen by the sender and proves nothing. Windows line endings
become "\n". The title is the first Markdown "# " heading, or else the file name without its extension.
"""
import re
from dataclasses import dataclass
from pathlib import PurePath

ALLOWED_EXTENSIONS = (".txt", ".md")
MAX_BYTES = 200 * 1024
MAX_TITLE = 200

WRONG_TYPE = "Only .txt and .md files can be uploaded."
TOO_BIG = "The file is larger than 200 KB."
NOT_UTF8 = "The file is not valid UTF-8 text."
BINARY = "The file looks binary (it contains NUL bytes)."
EMPTY = "The file is empty."


class ExtractError(ValueError):
    """The message is one of the fixed texts above; it never repeats the file's content."""


@dataclass(frozen=True)
class ExtractedText:
    title: str
    text: str


def extract_text(filename, data):
    name = PurePath(filename or "").name
    stem, suffix = PurePath(name).stem, PurePath(name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS or not stem or stem.startswith("."):
        raise ExtractError(WRONG_TYPE)
    if len(data) > MAX_BYTES:
        raise ExtractError(TOO_BIG)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ExtractError(NOT_UTF8) from None
    if "\x00" in text:
        raise ExtractError(BINARY)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise ExtractError(EMPTY)
    heading = re.search(r"^#\s+(.+?)\s*#*\s*$", text, re.M)
    title = (heading.group(1) if heading else stem).strip()[:MAX_TITLE]
    return ExtractedText(title=title, text=text)
