from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.models.obra import Obra
from app.models.relatorio import RelatorioSemanal
from app.schemas.relatorio_schema import RelatorioCreate, RelatorioDetalhe, RelatorioRead, RelatorioUpdate


router = APIRouter(tags=["Relatórios"])
settings = get_settings()


def _resolver_html_path(html_path: str | None) -> Path:
    if not html_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relatório ainda não possui HTML renderizado.",
        )

    path = Path(html_path)

    if path.is_absolute():
        return path

    return settings.output_path / path


def _obter_relatorio_ou_404(relatorio_id: int, db: Session) -> RelatorioSemanal:
    relatorio = db.get(RelatorioSemanal, relatorio_id)

    if not relatorio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relatório não encontrado.",
        )

    return relatorio


@router.get("/api/relatorios", response_model=list[RelatorioRead])
def listar_relatorios(
    obra_id: int | None = Query(default=None),
    status_relatorio: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[RelatorioSemanal]:
    stmt = select(RelatorioSemanal).order_by(RelatorioSemanal.data_referencia.desc())

    if obra_id is not None:
        stmt = stmt.where(RelatorioSemanal.obra_id == obra_id)

    if status_relatorio:
        stmt = stmt.where(RelatorioSemanal.status == status_relatorio)

    return list(db.scalars(stmt).all())


@router.post("/api/relatorios", response_model=RelatorioRead, status_code=status.HTTP_201_CREATED)
def criar_relatorio(payload: RelatorioCreate, db: Session = Depends(get_db)) -> RelatorioSemanal:
    obra = db.get(Obra, payload.obra_id)

    if not obra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Obra não encontrada para criação do relatório.",
        )

    relatorio = RelatorioSemanal(**payload.model_dump())
    db.add(relatorio)
    db.commit()
    db.refresh(relatorio)

    return relatorio


@router.get("/api/relatorios/{relatorio_id}", response_model=RelatorioDetalhe)
def obter_relatorio(relatorio_id: int, db: Session = Depends(get_db)) -> RelatorioSemanal:
    stmt = (
        select(RelatorioSemanal)
        .where(RelatorioSemanal.id == relatorio_id)
        .options(selectinload(RelatorioSemanal.etapas))
    )

    relatorio = db.scalars(stmt).first()

    if not relatorio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relatório não encontrado.",
        )

    return relatorio


@router.put("/api/relatorios/{relatorio_id}", response_model=RelatorioRead)
def atualizar_relatorio(
    relatorio_id: int,
    payload: RelatorioUpdate,
    db: Session = Depends(get_db),
) -> RelatorioSemanal:
    relatorio = _obter_relatorio_ou_404(relatorio_id, db)

    dados = payload.model_dump(exclude_unset=True)

    for campo, valor in dados.items():
        setattr(relatorio, campo, valor)

    db.add(relatorio)
    db.commit()
    db.refresh(relatorio)

    return relatorio


@router.get("/api/obras/{obra_id}/relatorios", response_model=list[RelatorioRead])
def listar_relatorios_da_obra(obra_id: int, db: Session = Depends(get_db)) -> list[RelatorioSemanal]:
    obra = db.get(Obra, obra_id)

    if not obra:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Obra não encontrada.",
        )

    stmt = (
        select(RelatorioSemanal)
        .where(RelatorioSemanal.obra_id == obra_id)
        .order_by(RelatorioSemanal.data_referencia.desc())
    )

    return list(db.scalars(stmt).all())


@router.get("/api/relatorios/{relatorio_id}/html", response_class=HTMLResponse)
def visualizar_html_relatorio(relatorio_id: int, db: Session = Depends(get_db)) -> FileResponse:
    relatorio = _obter_relatorio_ou_404(relatorio_id, db)
    html_path = _resolver_html_path(relatorio.html_path)

    if not html_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo HTML não encontrado no storage local.",
        )

    return FileResponse(
        path=html_path,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'inline; filename="{html_path.name}"',
            "Cache-Control": "no-cache",
        },
    )


@router.get("/api/relatorios/{relatorio_id}/download")
def baixar_html_relatorio(relatorio_id: int, db: Session = Depends(get_db)) -> FileResponse:
    relatorio = _obter_relatorio_ou_404(relatorio_id, db)
    html_path = _resolver_html_path(relatorio.html_path)

    if not html_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo HTML não encontrado no storage local.",
        )

    return FileResponse(
        path=html_path,
        media_type="text/html; charset=utf-8",
        filename="relatorio_semanal_obra.html",
        content_disposition_type="attachment",
    )
