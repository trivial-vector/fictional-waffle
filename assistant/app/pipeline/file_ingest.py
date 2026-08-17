"""Text extraction for message attachments (the web UI's attach-file button).

Scope is deliberately narrow: plain text, Markdown, and PDF (text-layer only
— no OCR, so a scanned/image-only PDF yields nothing useful). Extracted text
is folded directly into the turn's user_message as a labeled block and flows
through the existing pipeline unchanged from there — there is no separate
"attachment" record type or storage; the file's content becomes part of the
conversation and gets picked up by the normal extraction pass like anything
else the user said. That's a real scoping decision, not an oversight: it
keeps the schema from this session's build unchanged, at the cost of not
retaining the original file or a pointer to it anywhere. Worth revisiting if
attachments turn out to matter enough to need their own evidence-backed
record type.
"""
from __future__ import annotations

_TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
_MAX_CHARS = 20_000  # crude cap so a huge file doesn't blow out the prompt


def extract_text(filename: str, content: bytes) -> str:
    lower = filename.lower()
    if any(lower.endswith(ext) for ext in _TEXT_EXTENSIONS):
        text = content.decode("utf-8", errors="replace")
    elif lower.endswith(".pdf"):
        text = _extract_pdf(content)
    else:
        return f"[Attached file '{filename}' — unsupported type, content not extracted.]"

    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + "\n[... truncated ...]"
    return text


def _extract_pdf(content: bytes) -> str:
    # Imported lazily so the rest of this module (and anything importing it)
    # doesn't require pypdf unless a PDF actually shows up.
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages).strip()
    if not text:
        return "[Attached PDF had no extractable text layer — likely a scan; OCR not implemented.]"
    return text


def format_attachment_block(filename: str, extracted_text: str) -> str:
    return f"\n\n[Attached file: {filename}]\n{extracted_text}"
