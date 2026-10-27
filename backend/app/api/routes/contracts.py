from pathlib import Path
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.contract import Contract
from app.repositories.contract_repository import (
    create_contract,
    delete_contract as delete_contract_record,
    get_contract as find_contract,
    list_contracts as get_contracts_page,
)
from app.schemas.answer import (
    AnalysisResponse,
    ChatRequest,
    ChatResponse,
    ContractDetail,
    ContractListResponse,
    ContractSummary,
    UploadResponse,
)
from app.services.contract_analysis_service import analyze_contract, answer_chat, cached_analysis
from app.services.document_service import DocumentError, extract_document
from app.services.local_llm_service import LLMOverloaded, LLMResponseError, LLMUnavailable

router = APIRouter()


def _summary(contract: Contract) -> ContractSummary:
    return ContractSummary(
        contract_id=contract.id,
        filename=contract.filename,
        uploaded_at=contract.uploaded_at.isoformat(),
        processing_status=contract.processing_status,
        page_count=contract.page_count,
        extraction_method=contract.extraction_method,
        analysis_status=contract.analysis_status,
    )


@router.post("/api/contracts/upload", response_model=UploadResponse, status_code=201)
async def upload_contract(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    original_name = (file.filename or "").replace("\\", "/").split("/")[-1].strip()
    safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", original_name).strip(" .")[:255]
    if not safe_name:
        raise HTTPException(status_code=400, detail="A valid filename is required.")
    upload_limit = min(settings.max_upload_bytes, 20 * 1024 * 1024)
    content = await file.read(upload_limit + 1)
    if len(content) > upload_limit:
        raise HTTPException(status_code=413, detail="The upload exceeds the 20 MB size limit.")

    try:
        extracted = await run_in_threadpool(extract_document, safe_name, content)
    except DocumentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if not extracted.text.strip():
        raise HTTPException(status_code=422, detail="The uploaded file contains no readable text.")

    contract_id = str(uuid4())
    suffix = Path(safe_name).suffix.lower()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    stored_path = settings.storage_dir / f"{contract_id}{suffix}"
    stored_path.write_bytes(content)
    contract = Contract(
        id=contract_id,
        filename=safe_name,
        file_path=str(stored_path),
        processing_status="completed",
        page_count=extracted.page_count,
        extraction_method=extracted.extraction_method,
        extracted_text=extracted.text,
        analysis_status="pending",
    )
    try:
        create_contract(db, contract)
    except Exception:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise

    # The assessment requires the five standard answers to start immediately on upload.
    analysis = await analyze_contract(contract, db)
    return UploadResponse(
        contract_id=contract.id,
        filename=contract.filename,
        page_count=contract.page_count,
        extraction_method=contract.extraction_method,
        processing_status=contract.processing_status,
        analysis_status=analysis.status,
        answers=analysis.answers,
    )


@router.post("/api/contracts/{contract_id}/analyze", response_model=AnalysisResponse)
async def analyze(contract_id: str, db: Session = Depends(get_db)):
    contract = find_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found.")
    if contract.processing_status != "completed":
        raise HTTPException(status_code=409, detail="Contract processing has not completed.")
    try:
        return await analyze_contract(contract, db)
    except (LLMUnavailable, LLMOverloaded, LLMResponseError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/api/contracts/{contract_id}/chat", response_model=ChatResponse)
async def chat(contract_id: str, request: ChatRequest, db: Session = Depends(get_db)):
    contract = find_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found.")
    if contract.processing_status != "completed":
        raise HTTPException(status_code=409, detail="Contract processing has not completed.")
    try:
        answer = await answer_chat(contract, request.question)
    except LLMOverloaded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (LLMUnavailable, LLMResponseError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatResponse(contract_id=contract_id, **answer.model_dump())


@router.get("/api/contracts", response_model=ContractListResponse)
def list_contracts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    contracts, total = get_contracts_page(db, page, page_size)
    return ContractListResponse(
        items=[_summary(contract) for contract in contracts],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/api/contracts/{contract_id}", response_model=ContractDetail)
def get_contract(contract_id: str, db: Session = Depends(get_db)):
    contract = find_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found.")
    results = cached_analysis(contract)
    return ContractDetail(
        **_summary(contract).model_dump(),
        answers=results.answers if results else None,
    )


@router.delete("/api/contracts/{contract_id}", status_code=204)
def delete_contract(contract_id: str, db: Session = Depends(get_db)):
    contract = find_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found.")
    file_path = Path(contract.file_path)
    try:
        if file_path.is_file():
            file_path.unlink()
        delete_contract_record(db, contract)
    except OSError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Contract data could not be fully deleted.") from exc
