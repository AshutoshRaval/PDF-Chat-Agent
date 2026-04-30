import fitz
import pdfplumber


def _has_text_layer(file_path: str) -> bool:
    doc = fitz.open(file_path)
    text = "".join(page.get_text().strip() for page in doc)
    return len(text) > 50


def _has_tables(file_path: str) -> bool:
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            if page.find_tables():
                return True
    return False


def _extract_standard(file_path: str) -> list[tuple[int, str]]:
    doc = fitz.open(file_path)
    return [(i + 1, page.get_text()) for i, page in enumerate(doc)]


def _extract_with_tables(file_path: str) -> list[tuple[int, str]]:
    pages = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            for table in page.extract_tables():
                for row in table:
                    row_text = " | ".join(cell or "" for cell in row)
                    text += f"\n{row_text}"
            pages.append((i + 1, text))
    return pages


def parse_pdf(file_path: str) -> list[tuple[int, str]]:
    if not _has_text_layer(file_path):
        # Scanned PDF — no text layer detected
        # OCR support can be added here (pytesseract) when needed
        raise ValueError(
            "This PDF appears to be scanned and has no text layer. "
            "OCR support is not yet enabled."
        )

    if _has_tables(file_path):
        return _extract_with_tables(file_path)

    return _extract_standard(file_path)
