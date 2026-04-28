import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_COLLECTION", "pdf_chunks")

from main import app


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def test_pdf_id():
    pdf_id = os.getenv("TEST_PDF_ID", "")
    if not pdf_id:
        pytest.skip("Set TEST_PDF_ID env variable to a pre-ingested PDF id")
    return pdf_id
