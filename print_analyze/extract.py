"""Find framing-standard callouts in the text layer of a construction print."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, List, Optional, Sequence, Tuple

import pymupdf

from .library import Standard, StandardsLibrary, normalize

# A token is a run of letters/digits that may contain "." or "-" inside it.
# "/", ",", "(", ")", "+", "&" and whitespace all separate callouts, so a stacked
# label like "C1.11/E1.2 (2)" yields "C1.11", "E1.2" and "2".
TOKEN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.\-]*[A-Za-z0-9])?")

# Quantity prefixes staking sheets put in front of a unit: "2-E1.2", "3xH1.1", "2*F1.6".
QTY_PREFIX_RE = re.compile(r"^\d{1,2}[-xX*]")

# Tokens that look like a standard code but are not in the library get reported so
# a missing standard is noticed instead of silently skipped.
DEFAULT_CANDIDATE_RE = r"^[A-Z]{1,4}\d{1,2}(?:[.\-]\d{1,3})+[A-Z]{0,3}$"


@dataclass
class Match:
    page: int  # 0-based page index in the print
    text: str  # text exactly as it appears on the print
    standard: Standard
    rect: pymupdf.Rect  # unrotated page coordinates (what links and drawings use)


@dataclass
class Unmatched:
    page: int
    text: str
    rect: pymupdf.Rect


def _lines(page: pymupdf.Page, textpage=None) -> Iterator[Tuple[str, List[pymupdf.Rect]]]:
    """Yield each text line with one bounding box per character."""
    raw = page.get_text("rawdict", textpage=textpage, flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    for block in raw["blocks"]:
        for line in block.get("lines", []):
            chars: List[str] = []
            boxes: List[pymupdf.Rect] = []
            for span in line["spans"]:
                for ch in span["chars"]:
                    chars.append(ch["c"])
                    boxes.append(pymupdf.Rect(ch["bbox"]))
            if chars:
                yield "".join(chars), boxes


def _union(boxes: Sequence[pymupdf.Rect]) -> pymupdf.Rect:
    r = pymupdf.Rect(boxes[0])
    for b in boxes[1:]:
        r |= b
    return r


def _resolve(text: str, library: StandardsLibrary) -> Tuple[Optional[Standard], int]:
    """Look up a token; returns (standard, number of leading chars to drop from the box)."""
    std = library.lookup(text)
    if std is not None:
        return std, 0
    m = QTY_PREFIX_RE.match(text)
    if m:
        std = library.lookup(text[m.end():])
        if std is not None:
            return std, m.end()
    return None, 0


def find_callouts(
    page: pymupdf.Page,
    library: StandardsLibrary,
    candidate_re: Optional[re.Pattern] = None,
    textpage=None,
) -> Tuple[List[Match], List[Unmatched]]:
    matches: List[Match] = []
    unmatched: List[Unmatched] = []
    for text, boxes in _lines(page, textpage):
        tokens = list(TOKEN_RE.finditer(text))
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            # Codes are sometimes drawn with a space in them ("VC 1.21"): try joining
            # this token with the next one when only whitespace separates them.
            if i + 1 < len(tokens):
                nxt = tokens[i + 1]
                gap = text[tok.end():nxt.start()]
                if gap and not gap.strip():
                    joined = text[tok.start():nxt.end()]
                    std = library.lookup(joined)
                    if std is not None:
                        matches.append(Match(page.number, joined, std, _union(boxes[tok.start():nxt.end()])))
                        i += 2
                        continue

            word = tok.group()
            std, skip = _resolve(word, library)
            if std is not None:
                start = tok.start() + skip
                matches.append(Match(page.number, word, std, _union(boxes[start:tok.end()])))
            elif candidate_re is not None and candidate_re.match(normalize(word)):
                unmatched.append(Unmatched(page.number, word, _union(boxes[tok.start():tok.end()])))
            i += 1
    return matches, unmatched


def page_textpage(page: pymupdf.Page, ocr: bool, ocr_dpi: int = 300):
    """Return an OCR text page for scanned sheets, or None to use the native text layer.

    CAD prints exported with SHX fonts often have no text layer at all (the letters
    are line work), so OCR is the only way to read them.
    """
    if not ocr:
        return None
    if page.get_text("text").strip():
        return None
    return page.get_textpage_ocr(dpi=ocr_dpi, full=True)
