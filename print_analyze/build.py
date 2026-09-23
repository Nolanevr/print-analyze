"""Assemble the interactive as-built: print + standards index + linked standard pages."""

from __future__ import annotations

import csv
import json
import re
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pymupdf

from .extract import DEFAULT_CANDIDATE_RE, Match, Unmatched, find_callouts, page_textpage
from .library import Standard, StandardsLibrary, natural_key

FONT = "helv"
BOLD = "hebo"
LINK_BLUE = (0.05, 0.25, 0.75)
HIGHLIGHT_STROKE = (0.95, 0.45, 0.0)
HIGHLIGHT_FILL = (1.0, 0.85, 0.2)


@dataclass
class BuildOptions:
    highlight: bool = True
    back_links: bool = True
    index_page: bool = True
    ocr: bool = False
    ocr_dpi: int = 300
    candidate_pattern: Optional[str] = DEFAULT_CANDIDATE_RE
    print_pages: Optional[Sequence[int]] = None  # 0-based; None = all


@dataclass
class BuildReport:
    output: Path
    print_page_count: int
    matches: List[Match] = field(default_factory=list)
    unmatched: List[Unmatched] = field(default_factory=list)
    # code -> (first, last) 0-based page in the output PDF
    standard_pages: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    ocr_pages: List[int] = field(default_factory=list)
    textless_pages: List[int] = field(default_factory=list)

    def standards_used(self) -> List[Standard]:
        seen = OrderedDict()
        for m in self.matches:
            seen.setdefault(m.standard.code, m.standard)
        return sorted(seen.values(), key=lambda s: natural_key(s.code))

    def to_dict(self) -> dict:
        return {
            "output": str(self.output),
            "print_pages": self.print_page_count,
            "standards": [
                {
                    "code": s.code,
                    "title": s.title,
                    "source": str(s.path),
                    "output_pages": [p + 1 for p in self.standard_pages.get(s.code, ())],
                    "callouts": sum(1 for m in self.matches if m.standard is s),
                    "sheets": sorted({m.page + 1 for m in self.matches if m.standard is s}),
                }
                for s in self.standards_used()
            ],
            "callouts": [
                {"sheet": m.page + 1, "text": m.text, "standard": m.standard.code, "rect": list(m.rect)}
                for m in self.matches
            ],
            "not_in_library": [
                {"sheet": u.page + 1, "text": u.text, "rect": list(u.rect)} for u in self.unmatched
            ],
            "ocr_pages": [p + 1 for p in self.ocr_pages],
            "pages_without_text": [p + 1 for p in self.textless_pages],
        }

    def write_json(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    def write_csv(self, path: Path) -> None:
        with Path(path).open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["sheet", "text_on_print", "standard", "title", "status", "x0", "y0", "x1", "y1"])
            for m in self.matches:
                w.writerow([m.page + 1, m.text, m.standard.code, m.standard.title, "linked", *(round(v, 1) for v in m.rect)])
            for u in self.unmatched:
                w.writerow([u.page + 1, u.text, "", "", "not in library", *(round(v, 1) for v in u.rect)])


def _sheet_name(page: pymupdf.Page) -> str:
    label = page.get_label() if hasattr(page, "get_label") else ""
    return f"Sheet {label}" if label else f"Sheet {page.number + 1}"


def _goto(page: pymupdf.Page, rect: pymupdf.Rect, target: int) -> None:
    page.insert_link({"kind": pymupdf.LINK_GOTO, "from": rect, "page": target, "to": pymupdf.Point(0, 0), "zoom": 0})


class _VisualWriter:
    """Writes text/links using coordinates as the page is *displayed*, even on rotated pages."""

    def __init__(self, page: pymupdf.Page):
        self.page = page
        self.derot = page.derotation_matrix

    def rect(self, r: pymupdf.Rect) -> pymupdf.Rect:
        return pymupdf.Rect(r) * self.derot

    def box(self, r: pymupdf.Rect, fill=(1, 1, 1), color=(0.3, 0.3, 0.3)) -> None:
        self.page.draw_rect(self.rect(r), color=color, fill=fill, width=0.6, overlay=True)

    def text(self, x: float, y: float, s: str, size: float = 9, font: str = FONT, color=(0, 0, 0)) -> float:
        """Draw text with its baseline at (x, y); returns the x after the text."""
        p = pymupdf.Point(x, y) * self.derot
        self.page.insert_text(p, s, fontsize=size, fontname=font, color=color, rotate=self.page.rotation)
        return x + pymupdf.get_text_length(s, fontname=font, fontsize=size)

    def link(self, x: float, y: float, s: str, target: int, size: float = 9, font: str = FONT) -> float:
        end = self.text(x, y, s, size=size, font=font, color=LINK_BLUE)
        _goto(self.page, self.rect(pymupdf.Rect(x - 1, y - size, end + 1, y + 3)), target)
        return end


def _add_back_banner(page: pymupdf.Page, std: Standard, sheets: List[Tuple[str, int]], index_page: Optional[int]) -> None:
    """Small box at the top-left of a standard page linking back to where it is used."""
    size = 8
    parts: List[Tuple[str, Optional[int]]] = [(f"{std.code}   ", None), ("Back to: ", None)]
    for i, (name, target) in enumerate(sheets):
        parts.append((name, target))
        if i < len(sheets) - 1:
            parts.append((", ", None))
    if index_page is not None:
        parts.append(("   |   ", None))
        parts.append(("Standards index", index_page))

    width = sum(pymupdf.get_text_length(t, fontname=BOLD if i == 0 else FONT, fontsize=size) for i, (t, _) in enumerate(parts))
    vis = page.rect
    width = min(width, vis.width - 24)
    w = _VisualWriter(page)
    w.box(pymupdf.Rect(8, 6, 8 + width + 12, 6 + size + 8), fill=(1, 1, 0.9))
    x, y = 14.0, 6 + size + 3
    for i, (t, target) in enumerate(parts):
        if target is None:
            x = w.text(x, y, t, size=size, font=BOLD if i == 0 else FONT)
        else:
            x = w.link(x, y, t, target, size=size)


def _write_index(
    out: pymupdf.Document,
    at: int,
    rows: List[Tuple[Standard, int, List[Tuple[str, int]], int]],
    title: str,
) -> List[int]:
    """Insert index page(s) at position ``at``; returns their page numbers.

    rows: (standard, first output page, [(sheet name, sheet page)], callout count)
    """
    per_page = 38
    chunks = [rows[i:i + per_page] for i in range(0, len(rows), per_page)] or [[]]
    pages = []
    for n, chunk in enumerate(chunks):
        page = out.new_page(at + n, width=612, height=792)
        pages.append(page.number)
        w = _VisualWriter(page)
        w.text(48, 60, title, size=16, font=BOLD)
        sub = "Click a standard to open it. Click a sheet to jump back to the print."
        w.text(48, 78, sub, size=9, color=(0.35, 0.35, 0.35))
        y = 108
        for label, x in (("Standard", 48), ("Description", 140), ("Qty", 360), ("Used on", 400)):
            w.text(x, y, label, size=9, font=BOLD)
        page.draw_line(pymupdf.Point(48, y + 4), pymupdf.Point(564, y + 4), color=(0.5, 0.5, 0.5), width=0.5)
        y += 20
        for std, first, sheets, count in chunk:
            w.link(48, y, std.code, first, size=10, font=BOLD)
            title_txt = std.title if len(std.title) <= 40 else std.title[:39] + "..."
            w.text(140, y, title_txt, size=9)
            w.text(360, y, str(count), size=9)
            x = 400.0
            for i, (name, target) in enumerate(sheets):
                if x > 540:
                    w.text(x, y, "...", size=9)
                    break
                x = w.link(x, y, name.replace("Sheet ", ""), target, size=9)
                if i < len(sheets) - 1:
                    x = w.text(x, y, ", ", size=9)
            y += 17
        if not rows:
            w.text(48, y, "No library standards were found on the print.", size=10)
        if len(chunks) > 1:
            w.text(48, 760, f"Page {n + 1} of {len(chunks)}", size=8, color=(0.4, 0.4, 0.4))
    return pages


def build_as_built(
    print_path: Path,
    library: StandardsLibrary,
    output_path: Path,
    options: Optional[BuildOptions] = None,
) -> BuildReport:
    opts = options or BuildOptions()
    candidate_re = re.compile(opts.candidate_pattern) if opts.candidate_pattern else None

    out = pymupdf.open(print_path)
    if out.needs_pass:
        raise ValueError(f"{print_path} is password protected")
    n_print = out.page_count
    report = BuildReport(output=Path(output_path), print_page_count=n_print)
    scan = range(n_print) if opts.print_pages is None else [p for p in opts.print_pages if 0 <= p < n_print]

    # 1. Read the print.
    for pno in scan:
        page = out[pno]
        tp = page_textpage(page, opts.ocr, opts.ocr_dpi)
        if tp is not None:
            report.ocr_pages.append(pno)
        elif not page.get_text("text").strip():
            report.textless_pages.append(pno)
            continue
        m, u = find_callouts(page, library, candidate_re, textpage=tp)
        report.matches.extend(m)
        seen = set()
        for item in u:  # one "not in library" entry per text per sheet
            if (item.page, item.text) not in seen:
                seen.add((item.page, item.text))
                report.unmatched.append(item)

    used = report.standards_used()
    sheets_by_std: Dict[str, List[int]] = defaultdict(list)
    for m in report.matches:
        if m.page not in sheets_by_std[m.standard.code]:
            sheets_by_std[m.standard.code].append(m.page)
    sheet_names = {p: _sheet_name(out[p]) for p in range(n_print)}

    # 2. Append each referenced standard once.
    sources: Dict[Path, pymupdf.Document] = {}
    for std in used:
        src = sources.get(std.path)
        if src is None:
            src = sources[std.path] = pymupdf.open(std.path)
        pages = std.pages if std.pages is not None else list(range(src.page_count))
        bad = [p + 1 for p in pages if not 0 <= p < src.page_count]
        if bad:
            raise ValueError(f"Standard {std.code}: page(s) {bad} not in {std.path} ({src.page_count} pages)")
        first = out.page_count
        for p in pages:
            out.insert_pdf(src, from_page=p, to_page=p, links=False, annots=True)
        report.standard_pages[std.code] = (first, out.page_count - 1)
    for src in sources.values():
        src.close()

    # 3. Index page(s) go between the print and the standards; shift standard pages.
    index_pages: List[int] = []
    if opts.index_page:
        n_index = max(1, -(-len(used) // 38))
        report.standard_pages = {c: (a + n_index, b + n_index) for c, (a, b) in report.standard_pages.items()}
        rows = [
            (
                std,
                report.standard_pages[std.code][0],
                [(sheet_names[p], p) for p in sorted(sheets_by_std[std.code])],
                sum(1 for m in report.matches if m.standard is std),
            )
            for std in used
        ]
        index_pages = _write_index(out, n_print, rows, "Framing Standards Used")
    index_target = index_pages[0] if index_pages else None

    # 4. Link every callout on the print to its standard.
    for m in report.matches:
        page = out[m.page]
        target = report.standard_pages[m.standard.code][0]
        hot = pymupdf.Rect(m.rect) + (-2, -2, 2, 2)
        if opts.highlight:
            page.draw_rect(hot, color=HIGHLIGHT_STROKE, fill=HIGHLIGHT_FILL, width=0.8, fill_opacity=0.25, stroke_opacity=0.9, overlay=True)
        _goto(page, hot, target)

    # 5. Back-links on standard pages.
    if opts.back_links:
        for std in used:
            first, last = report.standard_pages[std.code]
            sheets = [(sheet_names[p], p) for p in sorted(sheets_by_std[std.code])]
            for pno in range(first, last + 1):
                _add_back_banner(out[pno], std, sheets, index_target)

    # 6. Bookmarks.
    toc = [[1, "Construction Print", 1]]
    toc += [[2, sheet_names[p], p + 1] for p in range(n_print)]
    if index_target is not None:
        toc.append([1, "Framing Standards Used", index_target + 1])
    if used:
        toc.append([1, "Framing Standards", report.standard_pages[used[0].code][0] + 1])
        toc += [[2, s.label, report.standard_pages[s.code][0] + 1] for s in used]
    out.set_toc(toc)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(output_path, garbage=3, deflate=True)
    out.close()
    return report
