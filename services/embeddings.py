from sentence_transformers import SentenceTransformer

_model = SentenceTransformer("all-MiniLM-L6-v2")


def embed_text(text: str) -> list[float]:
    return _model.encode(text).tolist()


def embed_chunks(chunks: list[str]) -> list[list[float]]:
    return [embedding.tolist() for embedding in _model.encode(chunks)]
