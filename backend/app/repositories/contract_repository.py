from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.contract import Contract


def get_contract(db: Session, contract_id: str) -> Contract | None:
    return db.get(Contract, contract_id)


def create_contract(db: Session, contract: Contract) -> Contract:
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return contract


def list_contracts(db: Session, page: int, page_size: int) -> tuple[list[Contract], int]:
    total = db.scalar(select(func.count()).select_from(Contract)) or 0
    contracts = db.scalars(
        select(Contract)
        .order_by(Contract.uploaded_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return contracts, total


def delete_contract(db: Session, contract: Contract) -> None:
    db.delete(contract)
    db.commit()
