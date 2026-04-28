import fitz  # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter
from services.embeddings import embed_chunks
from services.vector_store import ensure_collection, upsert_chunks

_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)


def parse_pdf_pages(file_path: str) -> list[tuple[int, str]]:
    doc = fitz.open(file_path)
    return [(i + 1, page.get_text()) for i, page in enumerate(doc)]


def ingest_pdf(file_path: str, pdf_id: str, filename: str = "") -> dict:
    ensure_collection()
    pages = parse_pdf_pages(file_path)

    all_chunks = []
    all_page_numbers = []
    for page_num, page_text in pages:
        page_chunks = _splitter.split_text(page_text)
        all_chunks.extend(page_chunks)
        all_page_numbers.extend([page_num] * len(page_chunks))

    embeddings = embed_chunks(all_chunks)
    upsert_chunks(all_chunks, embeddings, pdf_id, filename, all_page_numbers)
    return {"pdf_id": pdf_id, "chunks_stored": len(all_chunks)}
