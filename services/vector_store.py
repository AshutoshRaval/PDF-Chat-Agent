import os
import uuid
from typing import Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from dotenv import load_dotenv

load_dotenv()

COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "pdf_chunks")
VECTOR_SIZE = 384  # all-MiniLM-L6-v2 dimensionality

client = QdrantClient(
    url=os.getenv("QDRANT_URL", "http://localhost:6333"),
    api_key=os.getenv("QDRANT_API_KEY"),
)


def ensure_collection():
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def upsert_chunks(chunks: list[str], embeddings: list[list[float]], pdf_id: str, filename: str = "", page_numbers: list[int] = None):
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload={
                "text": chunk,
                "pdf_id": pdf_id,
                "chunk_index": i,
                "filename": filename,
                "page_number": page_numbers[i] if page_numbers else None,
            },
        )
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]
    client.upsert(collection_name=COLLECTION_NAME, points=points)


def list_documents() -> list[dict]:
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        return []
    seen = {}
    offset = None
    while True:
        results, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in results:
            pdf_id = point.payload.get("pdf_id")
            if pdf_id and pdf_id not in seen:
                seen[pdf_id] = point.payload.get("filename", "unknown")
        if offset is None:
            break
    return [{"pdf_id": k, "filename": v} for k, v in seen.items()]


def delete_document(pdf_id: str):
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=Filter(
            must=[FieldCondition(key="pdf_id", match=MatchValue(value=pdf_id))]
        ),
    )


def search(query_embedding: list[float], pdf_id: Optional[str] = None, limit: int = 5) -> list[dict]:
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        return []

    query_filter = None
    if pdf_id:
        query_filter = Filter(
            must=[FieldCondition(key="pdf_id", match=MatchValue(value=pdf_id))]
        )

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        query_filter=query_filter,
        limit=limit,
    ).points
    return [
        {
            "text": r.payload["text"],
            "score": r.score,
            "pdf_id": r.payload["pdf_id"],
            "filename": r.payload.get("filename", ""),
            "page_number": r.payload.get("page_number"),
        }
        for r in results
    ]
