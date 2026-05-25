from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.relatorio import RelatorioEtapa, RelatorioSemanal
from app.schemas.pipeline_schema import PipelineProcessResponse, PipelineStatusResponse
from app.services.pipeline_service import PipelineService, parse_data_referencia

router = APIRouter(prefix="/api/pipeline", tags=["Pipeline"])


@router.post("/processar", response_model=PipelineProcessResponse)
async def processar_relatorio(
    obra_id: int = Form(...),
    numero_ata: str | None = Form(None),
    data_referencia: str = Form(...),
    semana_referencia: str | None = Form(None),
    observacoes: str | None = Form(None),
    conteudo_whatsapp: str | None = Form(None),
    conteudo_transcricao: str | None = Form(None),
    arquivos: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data_ref = parse_data_referencia(data_referencia)
        service = PipelineService(db)
        return await service.processar(
            obra_id=obra_id,
            numero_ata=numero_ata,
            data_referencia=data_ref,
            arquivos=arquivos,
            conteudo_whatsapp=conteudo_whatsapp,
            conteudo_transcricao=conteudo_transcricao,
            semana_referencia=semana_referencia,
            observacoes=observacoes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao processar pipeline: {exc}") from exc


@router.get("/{relatorio_id}/status", response_model=PipelineStatusResponse)
def status_pipeline(relatorio_id: int, db: Session = Depends(get_db)) -> PipelineStatusResponse:
    relatorio = db.get(RelatorioSemanal, relatorio_id)
    if not relatorio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relatório não encontrado.")

    etapas = db.scalars(
        select(RelatorioEtapa)
        .where(RelatorioEtapa.relatorio_id == relatorio_id)
        .order_by(RelatorioEtapa.created_at.asc(), RelatorioEtapa.etapa_numero.asc())
    ).all()

    return PipelineStatusResponse(relatorio_id=relatorio.id, status=relatorio.status, etapas=list(etapas))


@router.post("/{relatorio_id}/reprocessar")
def reprocessar_pipeline(relatorio_id: int, db: Session = Depends(get_db)) -> dict:
    relatorio = db.get(RelatorioSemanal, relatorio_id)
    if not relatorio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relatório não encontrado.")

    return {
        "relatorio_id": relatorio_id,
        "status": "nao_implementado",
        "mensagem": "O reprocessamento reaproveitando anexos salvos será implementado após a tela de revisão da pipeline.",
    }
