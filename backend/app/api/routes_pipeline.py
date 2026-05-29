from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.models.relatorio import RelatorioEtapa, RelatorioSemanal
from app.schemas.pipeline_schema import PipelineProcessResponse, PipelineStatusResponse
from app.services.pipeline_service import PipelineService, parse_data_referencia
from app.services.storage_service import StoredFileContext

router = APIRouter(prefix="/api/pipeline", tags=["Pipeline"])

class ReprocessarPipelineRequest(BaseModel):
    instrucoes: str | None = None



async def _executar_pipeline_background(
    relatorio_id: int,
    stored_files: list[StoredFileContext],
    conteudo_whatsapp: str | None,
    conteudo_transcricao: str | None,
    semana_referencia: str | None,
    observacoes: str | None,
) -> None:
    """Executa a pipeline pesada fora da request HTTP.

    Uma nova sessão é aberta porque a sessão da request é encerrada quando a API
    responde ao frontend. Isso permite ao usuário ver o status evoluindo em tempo real.
    """
    db = SessionLocal()
    try:
        service = PipelineService(db)
        await service.continuar_processamento(
            relatorio_id=relatorio_id,
            stored_files=stored_files,
            conteudo_whatsapp=conteudo_whatsapp,
            conteudo_transcricao=conteudo_transcricao,
            semana_referencia=semana_referencia,
            observacoes=observacoes,
        )
    finally:
        db.close()


async def _executar_reprocessamento_background(
    relatorio_id: int,
    instrucoes: str,
) -> None:
    """Executa o reprocessamento fora da request para permitir progresso visual."""
    db = SessionLocal()
    try:
        service = PipelineService(db)
        await service.reprocessar_com_instrucoes(
            relatorio_id=relatorio_id,
            instrucoes=instrucoes,
        )
    finally:
        db.close()


@router.post("/processar", response_model=PipelineProcessResponse)
async def processar_relatorio(
    background_tasks: BackgroundTasks,
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
        relatorio, stored_files = await service.iniciar_processamento(
            obra_id=obra_id,
            numero_ata=numero_ata,
            data_referencia=data_ref,
            arquivos=arquivos,
        )

        background_tasks.add_task(
            _executar_pipeline_background,
            relatorio.id,
            stored_files,
            conteudo_whatsapp,
            conteudo_transcricao,
            semana_referencia,
            observacoes,
        )

        return {
            "relatorio_id": relatorio.id,
            "status": relatorio.status,
            "report_json": None,
            "html_path": None,
            "etapas": [
                {
                    "etapa_numero": etapa.etapa_numero,
                    "etapa_nome": etapa.etapa_nome,
                    "status": etapa.status,
                    "erro": etapa.erro,
                }
                for etapa in sorted(relatorio.etapas, key=lambda item: item.etapa_numero)
            ],
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao iniciar pipeline: {exc}") from exc


@router.get("/{relatorio_id}/status", response_model=PipelineStatusResponse)
def status_pipeline(relatorio_id: int, db: Session = Depends(get_db)) -> PipelineStatusResponse:
    relatorio = db.get(RelatorioSemanal, relatorio_id)
    if not relatorio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relatório não encontrado.")

    etapas = db.scalars(
        select(RelatorioEtapa)
        .where(RelatorioEtapa.relatorio_id == relatorio_id)
        .order_by(RelatorioEtapa.etapa_numero.asc())
    ).all()

    return PipelineStatusResponse(relatorio_id=relatorio.id, status=relatorio.status, etapas=list(etapas))


@router.post("/{relatorio_id}/reprocessar")
async def reprocessar_pipeline(
    relatorio_id: int,
    background_tasks: BackgroundTasks,
    payload: ReprocessarPipelineRequest,
    db: Session = Depends(get_db),
) -> dict:
    relatorio = db.get(RelatorioSemanal, relatorio_id)
    if not relatorio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relatório não encontrado.")

    instrucoes = (payload.instrucoes or "").strip()
    if not instrucoes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Informe as mudanças desejadas antes de reprocessar.")

    try:
        service = PipelineService(db)
        response = service.iniciar_reprocessamento(
            relatorio_id=relatorio_id,
            instrucoes=instrucoes,
        )
        background_tasks.add_task(_executar_reprocessamento_background, relatorio_id, instrucoes)
        return response
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao iniciar reprocessamento: {exc}") from exc
