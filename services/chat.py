import os
from anthropic import Anthropic
from dotenv import load_dotenv
from typing import Optional
from sentence_transformers import CrossEncoder
from services.embeddings import embed_text
from services.vector_store import search

load_dotenv()

_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"

# Cross-encoder for re-ranking retrieved chunks
_reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

SYSTEM_PROMPT = (
    "You are a document assistant. You answer questions ONLY based on the provided document context. "
    "If the question is unrelated to the document content — such as general knowledge, math, science, "
    "coding concepts, or anything not found in the context — respond with exactly: "
    "'I can only answer questions about the uploaded documents. Please ask something related to the document.' "
    "Do not answer general knowledge questions under any circumstances. "
    "If the answer is not found in the context, say so clearly. Do not make up information."
)

HISTORY_WINDOW = 6  # last 6 messages = 3 Q&A pairs
RETRIEVE_K = 10     # fetch more candidates for re-ranker to score
RERANK_TOP_K = 5    # return top 5 after re-ranking


def _expand_query(question: str) -> str:
    """Rewrite a vague or short query into a more specific search query."""
    response = _client.messages.create(
        model=MODEL,
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": (
                "Rewrite the following question as a detailed search query to improve document retrieval. "
                "Return only the rewritten query, nothing else.\n\n"
                f"Question: {question}"
            ),
        }],
    )
    return response.content[0].text.strip()


def _rerank(question: str, chunks: list) -> list:
    """Re-rank chunks using a cross-encoder and return top RERANK_TOP_K."""
    pairs = [(question, c["text"]) for c in chunks]
    scores = _reranker.predict(pairs)
    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in ranked[:RERANK_TOP_K]]


def answer_question(question: str, pdf_id: Optional[str] = None, history: list = []) -> dict:
    # Step 1 — expand query for better retrieval on vague/short questions
    expanded_query = _expand_query(question)

    # Step 2 — retrieve more candidates than needed (RETRIEVE_K)
    query_embedding = embed_text(expanded_query)
    chunks = search(query_embedding, pdf_id=pdf_id, limit=RETRIEVE_K)

    if not chunks:
        return {"answer": "No relevant content found in the document.", "sources": []}

    # Step 3 — re-rank candidates against the original question, keep top 5
    chunks = _rerank(question, chunks)

    # Step 4 — build prompt and call Claude
    context = "\n\n".join([f"[{i+1}] {c['text']}" for i, c in enumerate(chunks)])
    messages = [{"role": m["role"], "content": m["content"]} for m in history[-HISTORY_WINDOW:]]
    messages.append({
        "role": "user",
        "content": f"Context from document:\n{context}\n\nQuestion: {question}",
    })

    response = _client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    sources = [
        {
            "text": c["text"],
            "filename": c.get("filename", ""),
            "page_number": c.get("page_number"),
            "score": round(c["score"], 3),
        }
        for c in chunks
    ]

    return {
        "answer": response.content[0].text,
        "sources": sources,
    }
