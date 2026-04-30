import re
from langchain_text_splitters import RecursiveCharacterTextSplitter
from services.embeddings import embed_chunks
from services.vector_store import ensure_collection, upsert_chunks
from services.pdf_parser import parse_pdf

# Structure-aware splitter — higher overlap keeps headings with their content
_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=150,
    separators=["\n\n", "\n", ". ", " "],
)

# Matches common section headings in manuals, resumes, reports
_HEADING_RE = re.compile(
    r"^(#{1,3}\s+.+|[A-Z][A-Z\s]{3,}|Chapter\s+\d+|Section\s+\d+|\d+\.\s+[A-Z].+)$",
    re.MULTILINE,
)


def _split_by_structure(text: str) -> list[str]:
    """Split on section headings first, then apply RecursiveCharacterTextSplitter within each section."""
    sections = _HEADING_RE.split(text)
    chunks = []
    for section in sections:
        if section.strip():
            chunks.extend(_splitter.split_text(section.strip()))
    return chunks if chunks else _splitter.split_text(text)


def ingest_pdf(file_path: str, pdf_id: str, filename: str = "") -> dict:
    ensure_collection()
    pages = parse_pdf(file_path)

    all_chunks = []
    all_page_numbers = []
    for page_num, page_text in pages:
        page_chunks = _split_by_structure(page_text)
        all_chunks.extend(page_chunks)
        all_page_numbers.extend([page_num] * len(page_chunks))

    embeddings = embed_chunks(all_chunks)
    upsert_chunks(all_chunks, embeddings, pdf_id, filename, all_page_numbers)
    return {"pdf_id": pdf_id, "chunks_stored": len(all_chunks)}
