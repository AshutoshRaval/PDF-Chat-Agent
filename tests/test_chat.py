"""
Golden dataset tests — verify known answers against a pre-ingested PDF.

Usage:
    TEST_PDF_ID=<your-pdf-id> pytest tests/test_chat.py -v
"""
import json
import pytest


def load_golden():
    with open("tests/golden_dataset.json") as f:
        return json.load(f)


class TestHealth:
    def test_health_endpoint(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_documents_endpoint(self, client):
        res = client.get("/documents")
        assert res.status_code == 200
        assert "documents" in res.json()


class TestChatBasic:
    def test_chat_returns_answer(self, client, test_pdf_id):
        res = client.post("/chat", json={
            "question": "What is this document about?",
            "pdf_id": test_pdf_id,
        })
        assert res.status_code == 200
        data = res.json()
        assert "answer" in data
        assert len(data["answer"]) > 10

    def test_chat_returns_sources(self, client, test_pdf_id):
        res = client.post("/chat", json={
            "question": "What is this document about?",
            "pdf_id": test_pdf_id,
        })
        data = res.json()
        assert "sources" in data
        assert len(data["sources"]) > 0

    def test_sources_have_page_numbers(self, client, test_pdf_id):
        res = client.post("/chat", json={
            "question": "What is this document about?",
            "pdf_id": test_pdf_id,
        })
        sources = res.json()["sources"]
        for src in sources:
            assert "page_number" in src
            assert "filename" in src
            assert "score" in src
            assert "text" in src

    def test_unknown_pdf_id_returns_no_content(self, client):
        res = client.post("/chat", json={
            "question": "What is this about?",
            "pdf_id": "non-existent-id-000",
        })
        assert res.status_code == 200
        assert "No relevant content" in res.json()["answer"]

    def test_chat_with_history(self, client, test_pdf_id):
        res = client.post("/chat", json={
            "question": "Can you elaborate more?",
            "pdf_id": test_pdf_id,
            "history": [
                {"role": "user", "content": "What is the person's name?"},
                {"role": "assistant", "content": "The person's name is Ashutosh Raval."},
            ],
        })
        assert res.status_code == 200
        assert len(res.json()["answer"]) > 0


class TestGoldenDataset:
    @pytest.mark.parametrize("case", load_golden())
    def test_golden_case(self, client, test_pdf_id, case):
        if case.get("check_sources_only"):
            res = client.post("/chat", json={
                "question": case["question"],
                "pdf_id": test_pdf_id,
            })
            assert res.status_code == 200
            assert len(res.json()["sources"]) > 0, f"No sources returned for: {case['question']}"
            return

        res = client.post("/chat", json={
            "question": case["question"],
            "pdf_id": test_pdf_id,
        })
        assert res.status_code == 200
        answer = res.json()["answer"].lower()

        missing = [kw for kw in case["expected_keywords"] if kw.lower() not in answer]
        assert not missing, (
            f"[{case['description']}]\n"
            f"Question: {case['question']}\n"
            f"Missing keywords: {missing}\n"
            f"Got answer: {res.json()['answer']}"
        )
