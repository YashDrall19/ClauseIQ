from app.schemas.answer import ModelAnswer, ModelBatchAnswer


def prepare_upload(monkeypatch):
    async def completed_analysis(contract, _db):
        from app.schemas.answer import AnalysisResponse
        return AnalysisResponse(contract_id=contract.id, status="completed", answers=[])

    monkeypatch.setattr("app.api.routes.contracts.analyze_contract", completed_analysis)


def test_upload_and_list_do_not_return_document_text(client, monkeypatch):
    prepare_upload(monkeypatch)
    response = client.post(
        "/api/contracts/upload",
        files={"file": ("sample.txt", b"Payment must be made within thirty days.", "text/plain")},
    )
    assert response.status_code == 201
    upload = response.json()
    assert upload["processing_status"] == "completed"
    assert upload["analysis_status"] == "completed"
    assert "extracted_text" not in upload

    listing = client.get("/api/contracts").json()
    assert listing["total"] == 1
    assert "extracted_text" not in listing["items"][0]
    assert listing["items"][0]["contract_id"] == upload["contract_id"]


def test_upload_rejects_unsupported_empty_and_oversized(client, monkeypatch, test_settings):
    prepare_upload(monkeypatch)
    unsupported = client.post(
        "/api/contracts/upload",
        files={"file": ("sample.exe", b"some bytes", "application/octet-stream")},
    )
    assert unsupported.status_code == 415

    empty = client.post(
        "/api/contracts/upload",
        files={"file": ("sample.txt", b"", "text/plain")},
    )
    assert empty.status_code == 400

    test_settings.max_upload_bytes = 4
    oversized = client.post(
        "/api/contracts/upload",
        files={"file": ("sample.txt", b"12345", "text/plain")},
    )
    assert oversized.status_code == 413


def test_contract_detail_and_delete_remove_stored_file(client, monkeypatch, test_settings):
    prepare_upload(monkeypatch)
    upload = client.post(
        "/api/contracts/upload",
        files={"file": ("stored.txt", b"Confidential text remains local.", "text/plain")},
    ).json()
    contract_id = upload["contract_id"]
    stored_file = test_settings.storage_dir / f"{contract_id}.txt"
    assert stored_file.is_file()

    detail = client.get(f"/api/contracts/{contract_id}")
    assert detail.status_code == 200
    assert detail.json()["filename"] == "stored.txt"
    assert "extracted_text" not in detail.json()

    deleted = client.delete(f"/api/contracts/{contract_id}")
    assert deleted.status_code == 204
    assert not stored_file.exists()
    assert client.get(f"/api/contracts/{contract_id}").status_code == 404


def test_missing_contract_and_invalid_chat_question(client):
    assert client.get("/api/contracts/missing-id").status_code == 404
    assert client.post("/api/contracts/missing-id/chat", json={"question": "   "}).status_code == 422
    assert client.post(
        "/api/contracts/missing-id/chat", json={"question": "Can this be terminated early?"}
    ).status_code == 404


def test_chat_retrieval_is_scoped_and_returns_verified_source(client, monkeypatch):
    prepare_upload(monkeypatch)
    upload = client.post(
        "/api/contracts/upload",
        files={"file": ("sample.txt", b"Either party may terminate on 30 days notice.", "text/plain")},
    ).json()
    contract_id = upload["contract_id"]
    chunk = type(
        "Chunk",
        (),
        {
            "chunk_id": "chunk-a",
            "page": 1,
            "section_title": "Termination",
            "text": "Either party may terminate on 30 days notice.",
        },
    )()

    def scoped_evidence(_contract):
        return [(chunk, 0.83)]

    async def answer(prompt, _model):
        assert contract_id in prompt or "Can it be terminated early?" in prompt
        return ModelAnswer(
            answer="Either party may terminate on 30 days notice.",
            found_in_contract=True,
            source_ids=["chunk-a"],
        )

    monkeypatch.setattr("app.services.contract_analysis_service._evidence", scoped_evidence)
    monkeypatch.setattr("app.services.contract_analysis_service.local_llm_service.generate", answer)
    response = client.post(
        f"/api/contracts/{contract_id}/chat",
        json={"question": "Can it be terminated early?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["found_in_contract"] is True
    assert payload["sources"][0]["excerpt"] == chunk.text


def test_five_answer_schema_validation_and_order(client, monkeypatch):
    async def batch(prompt, model):
        assert model is ModelBatchAnswer
        ids = ["parties", "duration", "payment_terms", "termination", "risks_liabilities"]
        return ModelBatchAnswer(
            answers=[
                ModelAnswer(
                    question_id=question_id,
                    answer="Not found in the available evidence.",
                    found_in_contract=False,
                    source_ids=[],
                )
                for question_id in ids
            ]
        )

    monkeypatch.setattr("app.services.contract_analysis_service.local_llm_service.generate", batch)
    upload = client.post(
        "/api/contracts/upload",
        files={"file": ("sample.txt", b"Brief contract text about services.", "text/plain")},
    ).json()
    assert upload["analysis_status"] == "completed"
    assert [answer["question_id"] for answer in upload["answers"]] == [
        "parties", "duration", "payment_terms", "termination", "risks_liabilities"
    ]
    response = client.post(f"/api/contracts/{upload['contract_id']}/analyze")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert [answer["question_id"] for answer in payload["answers"]] == [
        "parties",
        "duration",
        "payment_terms",
        "termination",
        "risks_liabilities",
    ]
    assert all(answer["answer"]["found_in_contract"] is False for answer in payload["answers"])
    assert all(answer["answer"]["sources"] == [] for answer in payload["answers"])
    detail = client.get(f"/api/contracts/{upload['contract_id']}")
    assert detail.json()["analysis_status"] == "completed"
    assert len(detail.json()["answers"]) == 5
