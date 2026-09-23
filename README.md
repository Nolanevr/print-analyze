# print-analyze

Turn a powerline construction print (staking sheet / plan & profile) into an
**interactive as-built PDF**:

1. Reads every sheet of the print and finds the framing-standard callouts
   (`C1.11`, `VC1.21`, `E1.2`, `F1.6`, `H1.1`, …).
2. Pulls exactly those standards (and nothing else) out of your standards
   library and appends them to the print.
3. Makes every callout on the print **clickable**. Click `C7.1` next to a pole
   and the PDF jumps to the C7.1 framing standard.
4. Stamps a small **"Back to: Sheet 1, Sheet 3 | Standards index"** bar on each
   standard page so you can get back to the print.
5. Adds a **Framing Standards Used** index page (standard, description, qty,
   sheets used on) and PDF bookmarks.
6. Reports anything that *looks* like a standard but isn't in your library
   (e.g. a typo, or a standard you haven't added yet).

The output is a normal PDF. The links work in Adobe Acrobat/Reader, Bluebeam,
Chrome/Edge, iPad viewers, and so on, with no plug-ins.

## Install

```bash
pip install -e .          # needs Python 3.9+, installs PyMuPDF
```

## Quick start

```bash
print-analyze PRINT.pdf --standards path/to/standards -o AS_BUILT.pdf --report callouts.csv
```

Try it on generated sample data:

```bash
python examples/make_sample.py
print-analyze examples/sample/print.pdf -s examples/sample/standards -o examples/output/as-built.pdf
```

```
Library: 9 standards
Print:   2 sheet(s), 17 callout(s) linked
  C7.1         x2   sheets 1, 2
  E1.2         x3   sheets 1, 2
  ...
Looks like a standard but not in library (1): C9.99
Wrote examples/output/as-built.pdf
```

## Setting up the standards library

### Option A: one PDF per standard (simplest)

```
standards/
  C1.11 - Three Phase Crossarm Tangent.pdf
  C7.1 - Three Phase Deadend.pdf       <- multi-page files are imported whole
  E1.2.pdf
  guying/F1.6 - Screw Anchor.pdf       <- sub-folders are fine
```

The code is the file name, or the part before ` - ` when the name also has a
description. Matching ignores upper/lower case and spaces, so `VC 1.21` on a
print matches `VC1.21.pdf`.

### Option B: one big standards book plus an index CSV

```csv
code,file,pages,title,aliases
C1.11,RUS_1728F-803.pdf,12-13,Three Phase Crossarm Tangent,C1-11
E1.2,RUS_1728F-810.pdf,4,Single Down Guy,
```

```bash
print-analyze PRINT.pdf --index standards/index.csv -o AS_BUILT.pdf
```

`pages` is 1-based (`12`, `12-13`, `12,15`). `aliases` (separated by `;`) covers
other spellings a designer might use for the same unit. You can use `--standards`
and `--index` together; index rows win.

## How callouts are recognized

The text on each sheet is split at spaces and at `/ , ( ) + &`, and each piece is
looked up in the library. The match has to be exact, so `C1.1` never matches
inside `C1.11` or `XC1.1`. This handles typical staking labels:

| On the print     | Linked to            |
|------------------|----------------------|
| `C1.11/E1.2 (2)` | C1.11 and E1.2       |
| `2-E1.2`, `3xH1.1` | E1.2, H1.1 (quantity prefix ignored) |
| `VC 1.21`        | VC1.21               |
| `45-3`, `POLE 101` | nothing (not in the library) |

Text that fits the pattern of a standard code but isn't in the library is listed
under "not in library". Change that pattern with `--candidate-pattern REGEX`
(or turn it off with `--candidate-pattern ''`).

Rotated sheets (11×17 exported sideways) are handled.

## Prints without a text layer (important for CAD exports)

The tool reads the PDF's text. If AutoCAD/MicroStation exported the print with
**SHX fonts**, the letters become line work and there is no text to read. The
tool warns you when this happens: `sheet(s) N have no text layer`. Fixes, from
best to worst:

1. Re-plot with TrueType fonts. In AutoCAD, set `PDFSHX=1` so SHX text is kept as
   searchable comments, or map the text styles to a TTF font.
2. Use `--ocr` (requires [Tesseract](https://tesseract-ocr.github.io/) to be
   installed). This works for scanned prints, but OCR can misread small text,
   so check the report.

A quick check: open the print and press Ctrl+F for a standard code. If the
search finds it, this tool will too.

## Options

| Option | Meaning |
|---|---|
| `-s / --standards DIR` | folder of standard PDFs |
| `-i / --index CSV` | index for standards books |
| `-o / --output` | output PDF (default `<print>_as-built.pdf`) |
| `--report file.csv/.json` | every callout with sheet, standard, and position |
| `--pages 1-3,5` | only scan these sheets |
| `--ocr`, `--ocr-dpi` | OCR sheets without text |
| `--no-highlight` | clickable but no orange highlight box |
| `--no-back-links` | don't stamp the "Back to" bar on standard pages |
| `--no-index` | skip the "Framing Standards Used" page |

## Using it from Python

```python
from print_analyze import StandardsLibrary, build_as_built, BuildOptions

lib = StandardsLibrary.load("standards/")
report = build_as_built("print.pdf", lib, "as-built.pdf", BuildOptions(highlight=True))
report.write_csv("callouts.csv")
```

## Development

```bash
pip install -e .[dev]
pytest
```
