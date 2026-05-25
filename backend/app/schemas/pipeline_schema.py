from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class PipelineProcessResponse(BaseModel):
    relatorio_id: int
    status: str
    report_json: dict[str, Any] | None = None
    html_path: str | None = None
    etapas: list[dict[str, Any]] = []


class PipelineEtapaStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    etapa_numero: int
    etapa_nome: str
    status: str
    erro: str | None = None
    modelo_usado: str | None = None
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    updated_at: datetime


class PipelineStatusResponse(BaseModel):
    relatorio_id: int
    status: str
    etapas: list[PipelineEtapaStatus]
