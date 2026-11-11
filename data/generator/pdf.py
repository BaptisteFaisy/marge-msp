"""Minimal pure-Python standard-library PDF generator (spec 19.1).

Produces valid text-only PDF 1.4 documents without any third-party library:
one Helvetica font, one content stream per page, a proper cross-reference
table. The CI workers have no reportlab, and the demo only needs text.
"""

from __future__ import annotations

LINES_PER_PAGE = 50
PAGE_HEIGHT = 792
FIRST_LINE_Y = 740
LEADING = 14

ACCENT_FOLDS: dict[str, str] = {
    "é": "e",
    "è": "e",
    "ê": "e",
    "ë": "e",
    "à": "a",
    "â": "a",
    "ä": "a",
    "î": "i",
    "ï": "i",
    "ô": "o",
    "ö": "o",
    "ù": "u",
    "û": "u",
    "ü": "u",
    "ç": "c",
    "É": "E",
    "È": "E",
    "Ê": "E",
    "Ë": "E",
    "À": "A",
    "Â": "A",
    "Î": "I",
    "Ï": "I",
    "Ô": "O",
    "Û": "U",
    "Ç": "C",
    "œ": "oe",
    "Œ": "OE",
    "«": '"',
    "»": '"',
    "’": "'",
    "‘": "'",
    "–": "-",
    "—": "-",
    "…": "...",
    "€": "EUR",
    "°": " deg",
    "§": "art.",
    "&": "et",
}
"""The base-14 Helvetica encoding is Latin-1: fold everything above ASCII.

The ``.txt`` twin of every contract keeps the real accents; the PDF is what the
demo shows on screen, so a folded glyph is enough there and it keeps the writer
to ~150 lines with no embedded font.
"""


def escape_pdf_text(text: str) -> str:
    """Escape PDF string delimiters and fold non-ASCII glyphs to ASCII."""
    out: list[str] = []
    for char in text:
        if char in ("\\", "(", ")"):
            out.append("\\" + char)
        elif char in ACCENT_FOLDS:
            out.append(ACCENT_FOLDS[char])
        elif ord(char) < 128:
            out.append(char)
        else:
            out.append("?")
    return "".join(out)


def split_into_pages(text: str, lines_per_page: int = LINES_PER_PAGE) -> list[list[str]]:
    """Cut the text into fixed-height pages (a long line still fits the width)."""
    pages: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        current.append(line.strip("\r"))
        if len(current) >= lines_per_page:
            pages.append(current)
            current = []
    if current or not pages:
        pages.append(current)
    return pages


def page_stream(lines: list[str]) -> bytes:
    """The content stream of one page: text block, one ``Tj`` per line."""
    commands = ["BT", "/F1 10 Tf", f"50 {FIRST_LINE_Y} Td", f"{LEADING} TL"]
    for index, line in enumerate(lines):
        prefix = "" if index == 0 else "T* "
        commands.append(f"{prefix}({escape_pdf_text(line)}) Tj")
    commands.append("ET")
    body = "\n".join(commands).encode("latin-1", errors="replace")
    return f"<< /Length {len(body)} >>\nstream\n".encode("latin-1") + body + b"\nendstream"


def _page_objects(pages: list[list[str]], font_id: int) -> list[bytes]:
    objects: list[bytes] = []
    for index, lines in enumerate(pages):
        content_id = 4 + index * 2
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 {PAGE_HEIGHT}] "
                f"/Contents {content_id} 0 R "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>"
            ).encode("latin-1")
        )
        objects.append(page_stream(lines))
    return objects


def _assemble(objects: list[bytes]) -> bytes:
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{number} 0 obj\n".encode("latin-1"))
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref_offset = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        out.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    out.extend(
        (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n").encode(
            "latin-1"
        )
    )
    return bytes(out)


def generate_pdf(text: str) -> bytes:
    """Generate minimal PDF 1.4 bytes from plain text."""
    pages = split_into_pages(text)
    font_id = 3 + len(pages) * 2
    kids = " ".join(f"{3 + index * 2} 0 R" for index in range(len(pages)))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("latin-1"),
    ]
    objects.extend(_page_objects(pages, font_id))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    return _assemble(objects)
