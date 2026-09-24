# print-analyze

Turn a powerline construction as-built into an **interactive PDF**. Tap a
structure number on the print and it jumps to that structure's framing standard.
Each standard has a link back to the sheet.

## As-Built Linker (no install)

`dist/as-built-linker.html` is a single file that runs in Chrome or Edge. It
needs no Python, no install and no internet connection. Your drawings are
processed on your own computer and never uploaded.

1. Download `dist/as-built-linker.html` and double-click it.
2. **Standards book:** choose the framing standards PDF, then click the structure
   number in the title block of the page shown. Every other page is read from the
   same spot. Fix anything wrong by typing in the table. Pages with no number are
   added to the structure before them, for standards that run several pages.
3. **Print:** choose the as-built PDF, then click one structure number on it.
   Only numbers of the same size are linked, so span lengths (`285'`), pole
   classes (`45-3`), wire sizes (`1/0`), pole IDs and notes are skipped.
4. **Check:** linked numbers show in orange. Click any box to switch it on or off.
5. **Build:** downloads `<print>_linked.pdf`, which contains:
   - the print, with each structure number highlighted and linked
   - a "Structures Used" index (structure, book page, quantity, sheets)
   - only the standard pages that are used, each with a "Back to sheet" bar
   - bookmarks

The tool remembers where the number sits in the title block and your filter
settings, so next time you only choose the two files, check, and build.

To see how it works, open the tool and choose **Try it with sample drawings**.

### Phones and tablets

The finished PDF uses standard PDF links, which open in Adobe Acrobat Reader
(iOS/Android), Bluebeam, the iPhone/iPad Files app and desktop browsers. Some
email-attachment previews don't follow links, so open the file in a PDF app.
Keep "Large tap areas for phones and tablets" on so numbers are easy to hit
with a finger.

### If nothing is found

The tool reads the PDF's text. AutoCAD prints plotted with SHX fonts have no
text (the letters are line work), and the tool says "No text found". Re-plot
with TrueType fonts, or set `PDFSHX` to 1 in AutoCAD. A quick check: press
Ctrl+F in the PDF and search for a structure number. If the search finds it,
the tool can too.

### Rebuilding the HTML file

```bash
cd web && npm install && node build.mjs   # writes dist/as-built-linker.html
node test.mjs                              # headless-Chromium end-to-end test
```

## Python command-line version

The original command-line tool, for letter/number codes such as `C1.11` or
`VC1.21` and for batch runs.

### Install

```bash
pip install -e .          # needs Python 3.9+, installs PyMuPDF
```

### Quick start

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

### Setting up the standards library

#### Option A: one PDF per standard (simplest)

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

#### Option B: one big standards book plus an index CSV

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

### How callouts are recognized

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

### Prints without a text layer (important for CAD exports)

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

### Options

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

### Using it from Python

```python
from print_analyze import StandardsLibrary, build_as_built, BuildOptions

lib = StandardsLibrary.load("standards/")
report = build_as_built("print.pdf", lib, "as-built.pdf", BuildOptions(highlight=True))
report.write_csv("callouts.csv")
```

### Development

```bash
pip install -e .[dev]
pytest
```
