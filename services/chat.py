import os
from anthropic import Anthropic
from dotenv import load_dotenv
from typing import Optional
from services.embeddings import embed_text
from services.vector_store import search

load_dotenv()

_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = (
    "You are a document assistant. You answer questions ONLY based on the provided document context. "
    "If the question is unrelated to the document content — such as general knowledge, math, science, "
    "coding concepts, or anything not found in the context — respond with exactly: "
    "'I can only answer questions about the uploaded documents. Please ask something related to the document.' "
    "Do not answer general knowledge questions under any circumstances. "
    "If the answer is not found in the context, say so clearly. Do not make up information."
)


HISTORY_WINDOW = 6  # last 6 messages = 3 Q&A pairs


def answer_question(question: str, pdf_id: Optional[str] = None, history: list = []) -> dict:
    query_embedding = embed_text(question)
    chunks = search(query_embedding, pdf_id=pdf_id, limit=5)

    if not chunks:
        return {"answer": "No relevant content found in the document.", "sources": []}

    context = "\n\n".join([f"[{i+1}] {c['text']}" for i, c in enumerate(chunks)])

    # sliding window over past messages + current question with fresh context
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
