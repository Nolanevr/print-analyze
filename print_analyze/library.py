"""The framing-standards library: which standard codes exist and where their pages live."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional


def normalize(code: str) -> str:
    """Key used to compare a print callout with a library code (case/whitespace-insensitive)."""
    return re.sub(r"\s+", "", code).upper()


def parse_page_spec(spec: str) -> List[int]:
    """Turn a 1-based spec like "3", "3-5" or "3,7-8" into 0-based page indexes."""
    pages: List[int] = []
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start) - 1, int(end)))
        else:
            pages.append(int(part) - 1)
    return pages


def natural_key(code: str):
    """Sort "C1.2" before "C1.11" and "A2" before "A10"."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", code.upper())]


@dataclass
class Standard:
    code: str
    path: Path
    pages: Optional[List[int]] = None  # 0-based; None means every page of the file
    title: str = ""
    aliases: List[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.code} - {self.title}" if self.title else self.code


class StandardsLibrary:
    def __init__(self) -> None:
        self._by_key: Dict[str, Standard] = {}

    def __len__(self) -> int:
        return len({id(s) for s in self._by_key.values()})

    def __contains__(self, token: str) -> bool:
        return normalize(token) in self._by_key

    def standards(self) -> List[Standard]:
        unique = {id(s): s for s in self._by_key.values()}
        return sorted(unique.values(), key=lambda s: natural_key(s.code))

    def add(self, standard: Standard) -> None:
        for name in [standard.code, *standard.aliases]:
            key = normalize(name)
            existing = self._by_key.get(key)
            if existing is not None and existing is not standard:
                raise ValueError(
                    f"Standard code/alias {name!r} is defined twice "
                    f"({existing.path} and {standard.path})"
                )
            self._by_key[key] = standard

    def lookup(self, token: str) -> Optional[Standard]:
        return self._by_key.get(normalize(token))

    @classmethod
    def load(
        cls,
        directory: Optional[Path] = None,
        index_csv: Optional[Path] = None,
    ) -> "StandardsLibrary":
        """Build a library from a folder of per-standard PDFs and/or an index CSV.

        Folder mode: every ``*.pdf`` (searched recursively) is one standard. The code is
        the file name, or the part before `` - `` if the name also carries a title,
        e.g. ``C1.11 - Single Phase Tangent.pdf``.

        Index mode: a CSV with columns ``code,file[,pages][,title][,aliases]`` so one
        big standards book can be split by page range. ``file`` is relative to the CSV,
        ``pages`` is 1-based (``12`` or ``12-14``), ``aliases`` is ``;``-separated.
        Index rows override folder entries with the same code.
        """
        lib = cls()
        entries: Dict[str, Standard] = {}

        if directory is not None:
            for pdf in sorted(Path(directory).rglob("*")):
                if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
                    continue
                code, _, title = pdf.stem.partition(" - ")
                entries[normalize(code)] = Standard(code=code.strip(), path=pdf, title=title.strip())

        if index_csv is not None:
            index_csv = Path(index_csv)
            with index_csv.open(newline="", encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                    if not row.get("code"):
                        continue
                    if not row.get("file"):
                        raise ValueError(f"{index_csv}: row for {row['code']!r} has no file")
                    path = Path(row["file"])
                    if not path.is_absolute():
                        path = index_csv.parent / path
                    aliases = [a.strip() for a in row.get("aliases", "").split(";") if a.strip()]
                    entries[normalize(row["code"])] = Standard(
                        code=row["code"],
                        path=path,
                        pages=parse_page_spec(row["pages"]) if row.get("pages") else None,
                        title=row.get("title", ""),
                        aliases=aliases,
                    )

        for standard in entries.values():
            if not standard.path.exists():
                raise FileNotFoundError(f"Standard {standard.code}: {standard.path} not found")
            lib.add(standard)
        return lib

    @classmethod
    def from_standards(cls, standards: Iterable[Standard]) -> "StandardsLibrary":
        lib = cls()
        for s in standards:
            lib.add(s)
        return lib
