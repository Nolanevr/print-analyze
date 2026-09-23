"""Generate a small fake staking print and standards library to try the tool on.

    python examples/make_sample.py            # writes examples/sample/
    print-analyze examples/sample/print.pdf -s examples/sample/standards -o examples/output/as-built.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

STANDARDS = {
    "A1.1": "Single Phase Tangent (0-5 deg)",
    "C1.11": "Three Phase Crossarm Tangent",
    "C2.21": "Three Phase Small Angle",
    "C7.1": "Three Phase Deadend",
    "VC1.21": "Vertical Three Phase Tangent",
    "E1.2": "Single Down Guy",
    "F1.6": "Screw Anchor",
    "H1.1": "Pole Ground",
    "M5.10": "Transformer Mounting",
}

# (pole no., callout lines) per sheet; the second sheet is a rotated 11x17.
SHEETS = [
    [
        ("101", ["C7.1", "2-E1.2", "F1.6", "H1.1"]),
        ("102", ["C1.11"]),
        ("103", ["C1.11 / H1.1"]),
        ("104", ["C2.21", "E1.2 (2)"]),
        ("105", ["VC 1.21", "M5.10"]),
        ("106", ["C9.99"]),  # not in the library -> reported as missing
    ],
    [
        ("201", ["VC1.21"]),
        ("202", ["A1.1", "H1.1"]),
        ("203", ["C7.1", "E1.2", "F1.6"]),
    ],
]


def make_print(path: Path) -> None:
    doc = pymupdf.open()
    for n, poles in enumerate(SHEETS):
        page = doc.new_page(width=1224, height=792)  # 17 x 11 in
        page.draw_rect(page.rect + (18, 18, -18, -18), width=1.5)
        page.draw_rect(pymupdf.Rect(900, 680, 1206, 774), width=1)
        page.insert_text((910, 705), "SAMPLE ELECTRIC CO-OP", fontsize=12, fontname="hebo")
        page.insert_text((910, 725), "3-PH LINE EXTENSION - STAKING SHEET", fontsize=9)
        page.insert_text((910, 745), f"SHEET {n + 1} OF {len(SHEETS)}", fontsize=9)
        y = 330
        xs = [110 + i * 180 for i in range(len(poles))]
        page.draw_line(pymupdf.Point(xs[0], y), pymupdf.Point(xs[-1], y), width=1.2)
        for x, (pole, lines) in zip(xs, poles):
            page.draw_circle(pymupdf.Point(x, y), 6, fill=(0, 0, 0))
            page.insert_text((x - 18, y - 16), f"POLE {pole}", fontsize=9, fontname="hebo")
            page.insert_text((x - 18, y + 24), "45-3", fontsize=8)
            for i, line in enumerate(lines):
                page.insert_text((x - 18, y + 42 + i * 13), line, fontsize=9)
        page.insert_text((60, 600), "NOTES: ALL CONSTRUCTION PER RUS BULLETIN 1728F-803. SPAN LENGTHS 300 FT TYP.", fontsize=8)
        if n == 1:
            page.set_rotation(90)
    doc.save(path)


def make_standard(path: Path, code: str, title: str) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.draw_rect(page.rect + (24, 24, -24, -24), width=1.2)
    page.insert_text((200, 120), code, fontsize=36, fontname="hebo")
    page.insert_text((200, 150), title.upper(), fontsize=11)
    # crude pole + crossarm sketch
    page.draw_line(pymupdf.Point(306, 250), pymupdf.Point(306, 650), width=6)
    page.draw_line(pymupdf.Point(200, 290), pymupdf.Point(412, 290), width=5)
    for x in (210, 306, 402):
        page.draw_circle(pymupdf.Point(x, 278), 8)
    page.draw_rect(pymupdf.Rect(360, 690, 564, 760), width=1)
    page.insert_text((370, 712), f"STANDARD {code}", fontsize=10, fontname="hebo")
    page.insert_text((370, 730), "MATERIAL LIST ON NEXT PAGE" if code == "C7.1" else "", fontsize=8)
    if code == "C7.1":  # two-page standard
        p2 = doc.new_page(width=612, height=792)
        p2.insert_text((72, 90), f"{code} MATERIAL LIST", fontsize=14, fontname="hebo")
        for i, item in enumerate(["Crossarm, 8 ft", "Deadend insulator (3)", "Bolt, 5/8 x 12", "Washer, square"]):
            p2.insert_text((72, 130 + i * 18), f"{chr(97 + i)}.  {item}", fontsize=10)
    doc.save(path)


def main(out_dir: Path) -> None:
    std_dir = out_dir / "standards"
    std_dir.mkdir(parents=True, exist_ok=True)
    make_print(out_dir / "print.pdf")
    for code, title in STANDARDS.items():
        make_standard(std_dir / f"{code} - {title}.pdf", code, title)
    print(f"Sample print and {len(STANDARDS)} standards written to {out_dir}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "sample")
