import csv
import json
import sys
from pathlib import Path

import pymupdf
import pytest

from print_analyze import BuildOptions, StandardsLibrary, build_as_built
from print_analyze.cli import main
from print_analyze.extract import find_callouts
from print_analyze.library import Standard, parse_page_spec

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import make_sample  # noqa: E402


@pytest.fixture
def sample(tmp_path):
    make_sample.main(tmp_path)
    return tmp_path


def _page_with(lines, rotation=0):
    doc = pymupdf.open()
    page = doc.new_page(width=792, height=612)
    for i, text in enumerate(lines):
        page.insert_text((72, 72 + i * 20), text, fontsize=10)
    page.set_rotation(rotation)
    return doc


def _lib(*codes, tmp_path):
    stds = []
    for c in codes:
        p = tmp_path / f"{c}.pdf"
        d = pymupdf.open()
        d.new_page()
        d.save(p)
        stds.append(Standard(code=c, path=p))
    return StandardsLibrary.from_standards(stds)


def test_callout_tokenizing(tmp_path):
    lib = _lib("C1.1", "C1.11", "E1.2", "VC1.21", "H1.1", tmp_path=tmp_path)
    doc = _page_with(["C1.11/E1.2 (2)", "2-E1.2  H1.1", "VC 1.21", "C1.111 XC1.1 45-3", "c1.1"])
    matches, unmatched = find_callouts(doc[0], lib, __import__("re").compile(r"^[A-Z]{1,4}\d{1,2}(?:[.\-]\d{1,3})+[A-Z]{0,3}$"))
    assert [(m.text, m.standard.code) for m in matches] == [
        ("C1.11", "C1.11"),
        ("E1.2", "E1.2"),
        ("2-E1.2", "E1.2"),
        ("H1.1", "H1.1"),
        ("VC 1.21", "VC1.21"),
        ("c1.1", "C1.1"),
    ]
    # C1.1 must not match inside C1.111 or XC1.1; those are reported instead.
    assert sorted(u.text for u in unmatched) == ["C1.111", "XC1.1"]
    # quantity prefix is excluded from the clickable box
    qty = next(m for m in matches if m.text == "2-E1.2")
    plain = doc[0].search_for("E1.2")
    assert any(abs(qty.rect.x0 - r.x0) < 0.5 and abs(qty.rect.y0 - r.y0) < 0.5 for r in plain)


def test_rotated_print_link_positions(tmp_path):
    lib = _lib("C7.1", tmp_path=tmp_path)
    src = tmp_path / "rot.pdf"
    _page_with(["POLE 5  C7.1"], rotation=90).save(src)
    out = tmp_path / "out.pdf"
    report = build_as_built(src, lib, out)
    assert len(report.matches) == 1
    page = pymupdf.open(out)[0]
    (link,) = page.get_links()
    # get_links reports displayed coordinates; the text found there must be the callout
    text_rect = page.search_for("C7.1")[0] * page.rotation_matrix
    assert link["from"].contains(text_rect)


def test_end_to_end_sample(sample, tmp_path):
    out = tmp_path / "as-built.pdf"
    lib = StandardsLibrary.load(sample / "standards")
    report = build_as_built(sample / "print.pdf", lib, out)

    codes = [s.code for s in report.standards_used()]
    assert codes == ["A1.1", "C1.11", "C2.21", "C7.1", "E1.2", "F1.6", "H1.1", "M5.10", "VC1.21"]
    assert [u.text for u in report.unmatched] == ["C9.99"]

    doc = pymupdf.open(out)
    # 2 print sheets + 1 index + 9 standards (C7.1 has 2 pages)
    assert doc.page_count == 2 + 1 + 10
    # Every callout links to the first page of its standard, and that page is the standard.
    for m in report.matches:
        first, _ = report.standard_pages[m.standard.code]
        targets = [l["page"] for l in doc[m.page].get_links()]
        assert first in targets
        assert f"STANDARD {m.standard.code}" in doc[first].get_text()
    # Multi-page standard is imported whole.
    first, last = report.standard_pages["C7.1"]
    assert last == first + 1 and "C7.1 MATERIAL LIST" in doc[last].get_text()
    # Standard pages link back to each sheet that uses them and to the index.
    back = {l["page"] for l in doc[first].get_links()}
    assert back == {0, 1, 2}
    # Index page lists and links every standard.
    index_links = {l["page"] for l in doc[2].get_links()}
    assert {report.standard_pages[c][0] for c in codes} <= index_links
    toc_titles = [t[1] for t in doc.get_toc()]
    assert "Framing Standards Used" in toc_titles and "C7.1 - Three Phase Deadend" in toc_titles


def test_index_csv_book_and_rotated_standard(tmp_path):
    book = tmp_path / "book.pdf"
    d = pymupdf.open()
    for code in ["X1", "C1.11", "C1.11-B", "E1.2"]:
        p = d.new_page()
        p.insert_text((72, 300), f"STANDARD {code}", fontsize=14)
    d[3].set_rotation(90)
    d.save(book)
    (tmp_path / "index.csv").write_text(
        "code,file,pages,title,aliases\n"
        "C1.11,book.pdf,2-3,Tangent,C1-11\n"
        "E1.2,book.pdf,4,Down Guy,\n"
    )
    src = tmp_path / "print.pdf"
    _page_with(["C1-11", "E1.2"]).save(src)
    lib = StandardsLibrary.load(index_csv=tmp_path / "index.csv")
    out = tmp_path / "out.pdf"
    report = build_as_built(src, lib, out, BuildOptions(index_page=False))
    assert [m.standard.code for m in report.matches] == ["C1.11", "E1.2"]
    doc = pymupdf.open(out)
    assert doc.page_count == 1 + 2 + 1
    assert "STANDARD C1.11" in doc[1].get_text() and "STANDARD C1.11-B" in doc[2].get_text()
    # banner on the rotated page reads left-to-right as displayed
    rot = doc[3]
    assert rot.rotation == 90
    banner = [s for b in rot.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"] if "Back to" in s["text"]]
    assert banner
    shown = pymupdf.Rect(banner[0]["bbox"]) * rot.rotation_matrix
    assert shown.y0 < 40 and shown.x0 < 80


def test_parse_page_spec():
    assert parse_page_spec("1,3-5") == [0, 2, 3, 4]


def test_cli(sample, tmp_path, capsys):
    out = tmp_path / "o.pdf"
    rep = tmp_path / "r.json"
    code = main([str(sample / "print.pdf"), "-s", str(sample / "standards"), "-o", str(out), "--report", str(rep)])
    assert code == 0 and out.exists()
    data = json.loads(rep.read_text())
    assert {s["code"] for s in data["standards"]} >= {"C7.1", "VC1.21"}
    assert data["not_in_library"][0]["text"] == "C9.99"
    assert "C9.99" in capsys.readouterr().out

    rep_csv = tmp_path / "r.csv"
    assert main([str(sample / "print.pdf"), "-s", str(sample / "standards"), "-o", str(out), "--report", str(rep_csv), "--pages", "2"]) == 0
    rows = list(csv.DictReader(rep_csv.open()))
    assert rows and {r["sheet"] for r in rows} == {"2"}
