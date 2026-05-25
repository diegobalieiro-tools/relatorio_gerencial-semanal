from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.obra import Obra
from app.models.relatorio import RelatorioSemanal
from app.schemas.obra_schema import ObraCreate, ObraListItem, ObraRead, ObraUpdate


router = APIRouter(prefix="/api/obras", tags=["Obras"])


@router.get("", response_model=list[ObraListItem])
def listar_obras(db: Session = Depends(get_db)) -> list[ObraListItem]:
    obras = db.scalars(select(Obra).order_by(Obra.created_at.desc())).all()

    resultado: list[ObraListItem] = []

    for obra in obras:
        relatorios_count = db.scalar(
            select(func.count(RelatorioSemanal.id)).where(RelatorioSemanal.obra_id == obra.id)
        ) or 0

        ultimo_relatorio = db.scalar(
            select(func.max(RelatorioSemanal.data_referencia)).where(RelatorioSemanal.obra_id == obra.id)
        )

        item = ObraListItem.model_validate(obra)
        item.relatorios_count = int(relatorios_count)
        item.ultimo_relatorio = ultimo_relatorio
        resultado.append(item)

    return resultado


@router.post("", response_model=ObraRead, status_code=status.HTTP_201_CREATED)
def criar_obra(payload: ObraCreate, db: Session = Depends(get_db)) -> Obra:
    obra = Obra(**payload.model_dump())
    db.add(obra)
    db.commit()
    db.refresh(obra)
    return obra


@router.get("/{obra_id}", response_model=ObraRead)
def obter_obra(obra_id: int, db: Session = Depends(get_db)) -> Obra:
    obra = db.get(Obra, obra_id)

    if not obra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Obra não encontrada.",
        )

    return obra


@router.put("/{obra_id}", response_model=ObraRead)
def atualizar_obra(obra_id: int, payload: ObraUpdate, db: Session = Depends(get_db)) -> Obra:
    obra = db.get(Obra, obra_id)

    if not obra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Obra não encontrada.",
        )

    dados = payload.model_dump(exclude_unset=True)

    for campo, valor in dados.items():
        setattr(obra, campo, valor)

    db.add(obra)
    db.commit()
    db.refresh(obra)

    return obra


@router.delete("/{obra_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_obra(obra_id: int, db: Session = Depends(get_db)) -> None:
    obra = db.get(Obra, obra_id)

    if not obra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Obra não encontrada.",
        )

    db.delete(obra)
    db.commit()
