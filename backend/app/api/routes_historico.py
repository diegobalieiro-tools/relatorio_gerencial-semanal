from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.obra import Obra
from app.services.history_service import (
    build_resumo_historico_normalizado,
    get_historico_itens,
    get_historico_pendencias,
    get_historico_pontos_criticos,
    get_historico_reprogramacoes,
    get_linha_tempo_item,
)

router = APIRouter(prefix="/api/obras/{obra_id}/historico", tags=["Histórico"])


def _check_obra(db: Session, obra_id: int) -> None:
    if not db.get(Obra, obra_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra não encontrada.")


@router.get("/resumo")
def resumo_historico(obra_id: int, db: Session = Depends(get_db)) -> dict:
    _check_obra(db, obra_id)
    return build_resumo_historico_normalizado(db, obra_id)


@router.get("/pendencias")
def historico_pendencias(obra_id: int, db: Session = Depends(get_db)) -> list[dict]:
    _check_obra(db, obra_id)
    return get_historico_pendencias(db, obra_id)


@router.get("/pontos-criticos")
def historico_pontos_criticos(obra_id: int, db: Session = Depends(get_db)) -> list[dict]:
    _check_obra(db, obra_id)
    return get_historico_pontos_criticos(db, obra_id)


@router.get("/reprogramacoes")
def historico_reprogramacoes(obra_id: int, db: Session = Depends(get_db)) -> list[dict]:
    _check_obra(db, obra_id)
    return get_historico_reprogramacoes(db, obra_id)


@router.get("/itens")
def historico_itens(obra_id: int, db: Session = Depends(get_db)) -> list[dict]:
    _check_obra(db, obra_id)
    return get_historico_itens(db, obra_id)


@router.get("/itens/{item_id}")
def historico_item(obra_id: int, item_id: int, db: Session = Depends(get_db)) -> list[dict]:
    _check_obra(db, obra_id)
    return get_linha_tempo_item(db, obra_id, item_id)
