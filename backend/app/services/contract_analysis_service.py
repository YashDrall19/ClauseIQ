import json
import logging

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.contract import Contract
from app.prompts.contract_prompts import answer_prompt, batch_prompt
from app.schemas.answer import (
    AnalysisItem,
    AnalysisResponse,
    Answer,
    ModelAnswer,
    ModelBatchAnswer,
    Source,
)
from app.services.local_llm_service import (
    LLMOverloaded,
    LLMResponseError,
    LLMUnavailable,
    local_llm_service,
)
from app.services.chunking_service import chunk_pages
from app.services.document_service import PageText


logger = logging.getLogger(__name__)
QUESTIONS = [
    ("parties", "What are the parties involved in this contract?"),
    ("duration", "What is the effective date and contract duration?"),
    ("payment_terms", "What are the payment terms and obligations?"),
    ("termination", "What are the termination conditions?"),
    ("risks_liabilities", "What are the key risks, penalties, or liability clauses?"),
]
NOT_FOUND = "The information could not be found in the available contract text."


def _evidence(contract: Contract) -> list[tuple[object, float]]:
    """Turn extracted document text into cited page chunks for the cloud AI request.

    This deliberately avoids local embeddings/FAISS: the chosen provider receives the extracted
    contract text directly and can cite only chunks that we supplied.
    """
    pages: list[PageText] = []
    current_page = 1
    current_lines: list[str] = []
    for line in contract.extracted_text.splitlines():
        if line.startswith("[Page ") and line.endswith("]"):
            if current_lines:
                pages.append(PageText(current_page, "\n".join(current_lines).strip()))
            try:
                current_page = int(line[6:-1])
            except ValueError:
                current_page = len(pages) + 1
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        pages.append(PageText(current_page, "\n".join(current_lines).strip()))
    chunks = chunk_pages(pages or [PageText(1, contract.extracted_text)])
    return [(chunk, 0.8) for chunk in chunks]


def _pack_evidence(results: list[tuple[object, float]], max_chars: int) -> list[dict]:
    packed = []
    used = 0
    for chunk, score in results:
        excerpt = chunk.text[: min(1800, max_chars - used)]
        if not excerpt:
            break
        packed.append(
            {
                "id": chunk.chunk_id,
                "page": chunk.page,
                "section_title": chunk.section_title,
                "text": excerpt,
                "similarity": round(score, 4),
            }
        )
        used += len(excerpt)
        if used >= max_chars:
            break
    return packed


def _validated_answer(model_answer: ModelAnswer, evidence: list[dict], scores: dict[str, float]) -> Answer:
    allowed = {item["id"]: item for item in evidence}
    cited = []
    for source_id in dict.fromkeys(model_answer.source_ids):
        item = allowed.get(source_id)
        if item is not None:
            cited.append(
                Source(
                    page=item["page"],
                    excerpt=item["text"],
                    section_title=item["section_title"],
                )
            )
    found = bool(model_answer.found_in_contract and cited)
    if not found:
        return Answer(
            answer=NOT_FOUND,
            confidence_score=0.0 if not evidence else 0.2,
            found_in_contract=False,
            sources=[],
        )
    score = max(scores.get(source_id, 0.0) for source_id in model_answer.source_ids if source_id in allowed)
    confidence = min(0.95, max(0.35, 0.45 + 0.4 * max(0.0, score)))
    return Answer(
        answer=model_answer.answer.strip(),
        confidence_score=round(confidence, 2),
        found_in_contract=True,
        sources=cited,
    )


async def analyze_contract(contract: Contract, db: Session, force: bool = False) -> AnalysisResponse:
    if contract.analysis_status == "completed" and contract.analysis_results and not force:
        return AnalysisResponse.model_validate_json(contract.analysis_results)

    settings = get_settings()
    grouped = {}
    scores_by_question: dict[str, dict[str, float]] = {}
    questions = [{"question_id": key, "question": text} for key, text in QUESTIONS]
    for question_id, question in QUESTIONS:
        results = _evidence(contract)
        packed = _pack_evidence(results, settings.max_ai_context_chars // len(QUESTIONS))
        grouped[question_id] = packed
        scores_by_question[question_id] = {item["id"]: score for item, (_, score) in zip(packed, results)}

    outputs: dict[str, AnalysisItem] = {}
    try:
        batch = await local_llm_service.generate(
            batch_prompt(questions, grouped), ModelBatchAnswer
        )
        by_id = {item.question_id: item for item in batch.answers}
        if len(by_id) != len(QUESTIONS) or set(by_id) != {key for key, _ in QUESTIONS}:
            raise LLMResponseError("Batch response did not include each requested question exactly once.")
        for question_id, question in QUESTIONS:
            answer = _validated_answer(by_id[question_id], grouped[question_id], scores_by_question[question_id])
            outputs[question_id] = AnalysisItem(
                question_id=question_id, question=question, status="completed", answer=answer
            )
    except LLMResponseError:
        logger.info("Batched analysis validation failed; falling back to individual questions")
        for question_id, question in QUESTIONS:
            evidence = grouped[question_id]
            if not evidence:
                outputs[question_id] = AnalysisItem(
                    question_id=question_id,
                    question=question,
                    status="completed",
                    answer=Answer(
                        answer=NOT_FOUND, confidence_score=0.0, found_in_contract=False, sources=[]
                    ),
                )
                continue
            try:
                result = await local_llm_service.generate(
                    answer_prompt(question, evidence), ModelAnswer
                )
                if result.question_id is not None and result.question_id != question_id:
                    raise LLMResponseError("The AI provider returned the wrong question identifier.")
                answer = _validated_answer(
                    result, evidence, scores_by_question[question_id]
                )
                outputs[question_id] = AnalysisItem(
                    question_id=question_id, question=question, status="completed", answer=answer
                )
            except (LLMResponseError, LLMUnavailable, LLMOverloaded) as exc:
                logger.warning("Analysis failed for question %s: %s", question_id, exc)
                outputs[question_id] = AnalysisItem(
                    question_id=question_id,
                    question=question,
                    status="failed",
                    error=f"AI provider failed for this question: {exc}",
                )
    except (LLMUnavailable, LLMOverloaded) as exc:
        logger.warning("Batched contract analysis could not run: %s", exc)
        outputs = {
            question_id: AnalysisItem(
                question_id=question_id,
                question=question,
                status="failed",
                error=f"AI provider is unavailable: {exc}",
            )
            for question_id, question in QUESTIONS
        }

    items = [outputs[question_id] for question_id, _ in QUESTIONS]
    failed = sum(item.status == "failed" for item in items)
    status = "failed" if failed == len(items) else "partial" if failed else "completed"
    response = AnalysisResponse(contract_id=contract.id, status=status, answers=items)
    contract.analysis_status = status
    contract.analysis_results = response.model_dump_json()
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return response


async def answer_chat(contract: Contract, question: str) -> Answer:
    settings = get_settings()
    results = _evidence(contract)
    evidence = _pack_evidence(results, settings.max_ai_context_chars)
    if not evidence:
        return Answer(
            answer=NOT_FOUND, confidence_score=0.0, found_in_contract=False, sources=[]
        )
    scores = {item["id"]: score for item, (_, score) in zip(evidence, results)}
    try:
        model_answer = await local_llm_service.generate(
            answer_prompt(question, evidence), ModelAnswer
        )
    except (LLMUnavailable, LLMOverloaded, LLMResponseError):
        raise
    return _validated_answer(model_answer, evidence, scores)


def cached_analysis(contract: Contract) -> AnalysisResponse | None:
    if not contract.analysis_results:
        return None
    try:
        return AnalysisResponse.model_validate_json(contract.analysis_results)
    except ValueError:
        return None
