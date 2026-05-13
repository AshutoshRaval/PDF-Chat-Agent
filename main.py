import os
import uuid
import inngest
import inngest.fast_api
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from functions.inngest_functions import inngest_client, process_pdf
from services.chat import answer_question
from services.vector_store import list_documents, delete_document

load_dotenv()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="PDF Chat Agent")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

inngest.fast_api.serve(app, inngest_client, [process_pdf])


class HistoryMessage(BaseModel):
    role: str
    content: str


class UserContext(BaseModel):
    user_id: str
    name: str
    role: str


class ChatRequest(BaseModel):
    question: str
    pdf_id: Optional[str] = None
    history: list[HistoryMessage] = []
    user_context: Optional[UserContext] = None


@app.post("/upload")
@limiter.limit("5/minute")
async def upload_pdf(request: Request, file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    pdf_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{pdf_id}.pdf")

    with open(file_path, "wb") as f:
        f.write(await file.read())

    await inngest_client.send(
        inngest.Event(
            name="pdf/ingest",
            data={"file_path": file_path, "pdf_id": pdf_id, "filename": file.filename},
        )
    )

    return {"pdf_id": pdf_id, "filename": file.filename, "message": "PDF received, ingestion started"}


@app.post("/chat")
@limiter.limit("10/minute")
def chat(request: Request, body: ChatRequest):
    history = [{"role": m.role, "content": m.content} for m in body.history]
    user_context = body.user_context.model_dump() if body.user_context else None
    return answer_question(body.question, pdf_id=body.pdf_id, history=history, user_context=user_context)


@app.get("/documents")
def documents():
    return {"documents": list_documents()}


@app.delete("/documents/{pdf_id}")
def delete_doc(pdf_id: str):
    delete_document(pdf_id)
    file_path = os.path.join(UPLOAD_DIR, f"{pdf_id}.pdf")
    if os.path.exists(file_path):
        os.remove(file_path)
    return {"deleted": pdf_id}


@app.get("/health")
def health():
    return {"status": "ok"}
