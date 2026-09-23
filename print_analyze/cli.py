"""Command line entry point: ``print-analyze PRINT.pdf --standards DIR -o AS_BUILT.pdf``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .build import BuildOptions, build_as_built
from .extract import DEFAULT_CANDIDATE_RE
from .library import StandardsLibrary, parse_page_spec


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="print-analyze",
        description=(
            "Find framing-standard callouts (e.g. C1.11, VC1.21, E1.2) on a powerline "
            "construction print and build an interactive as-built PDF: the print, an index "
            "of standards used, and each standard's drawing, with every callout clickable."
        ),
    )
    p.add_argument("print_pdf", type=Path, help="construction print / staking sheet PDF")
    p.add_argument("-s", "--standards", type=Path, help="folder of standard PDFs, one file per standard (file name = code)")
    p.add_argument("-i", "--index", type=Path, help="CSV index (code,file,pages,title,aliases) for standards books")
    p.add_argument("-o", "--output", type=Path, help="output PDF (default: <print>_as-built.pdf)")
    p.add_argument("--report", type=Path, help="also write a report (.json or .csv) of every callout found")
    p.add_argument("--pages", help="only scan these print pages, 1-based (e.g. 1-3,5)")
    p.add_argument("--ocr", action="store_true", help="OCR print pages that have no text layer (needs Tesseract)")
    p.add_argument("--ocr-dpi", type=int, default=300)
    p.add_argument("--no-highlight", action="store_true", help="make callouts clickable without drawing a highlight box")
    p.add_argument("--no-back-links", action="store_true", help="do not stamp 'Back to' links on standard pages")
    p.add_argument("--no-index", action="store_true", help="do not add the 'Framing Standards Used' index page")
    p.add_argument(
        "--candidate-pattern",
        default=DEFAULT_CANDIDATE_RE,
        help="regex for text that looks like a standard code; matches not in the library are "
        "reported as missing (use '' to disable)",
    )
    return p


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if not args.standards and not args.index:
        print("error: give --standards DIR and/or --index CSV", file=sys.stderr)
        return 2
    if not args.print_pdf.exists():
        print(f"error: {args.print_pdf} not found", file=sys.stderr)
        return 2

    library = StandardsLibrary.load(args.standards, args.index)
    if len(library) == 0:
        print("error: no standards found in the library", file=sys.stderr)
        return 2

    output = args.output or args.print_pdf.with_name(args.print_pdf.stem + "_as-built.pdf")
    opts = BuildOptions(
        highlight=not args.no_highlight,
        back_links=not args.no_back_links,
        index_page=not args.no_index,
        ocr=args.ocr,
        ocr_dpi=args.ocr_dpi,
        candidate_pattern=args.candidate_pattern or None,
        print_pages=parse_page_spec(args.pages) if args.pages else None,
    )
    try:
        report = build_as_built(args.print_pdf, library, output, opts)
    except Exception as exc:  # show a clean message for bad input files
        if "tesseract" in str(exc).lower():
            print("error: --ocr needs Tesseract installed (https://tesseract-ocr.github.io/)", file=sys.stderr)
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1

    used = report.standards_used()
    print(f"Library: {len(library)} standards")
    print(f"Print:   {report.print_page_count} sheet(s), {len(report.matches)} callout(s) linked")
    for std in used:
        n = sum(1 for m in report.matches if m.standard is std)
        sheets = sorted({m.page + 1 for m in report.matches if m.standard is std})
        print(f"  {std.code:<12} x{n:<3} sheets {', '.join(map(str, sheets))}")
    if report.unmatched:
        missing = sorted({u.text for u in report.unmatched})
        print(f"Looks like a standard but not in library ({len(missing)}): {', '.join(missing)}")
    if report.textless_pages:
        pages = ", ".join(str(p + 1) for p in report.textless_pages)
        print(f"WARNING: sheet(s) {pages} have no text layer; re-export the print with TrueType text or use --ocr")
    if report.ocr_pages:
        print(f"OCR used on sheet(s): {', '.join(str(p + 1) for p in report.ocr_pages)}")
    print(f"Wrote {output}")

    if args.report:
        if args.report.suffix.lower() == ".csv":
            report.write_csv(args.report)
        else:
            report.write_json(args.report)
        print(f"Wrote {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
