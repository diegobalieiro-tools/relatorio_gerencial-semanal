from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RelatorioBase(BaseModel):
    obra_id: int
    numero_ata: str | None = Field(default=None, max_length=50)
    data_referencia: date

    titulo: str = Field(default="Relatório Semanal de Obra", max_length=255)
    status: str = Field(default="rascunho", max_length=50)

    report_json: dict[str, Any] | None = None
    html_path: str | None = None
    template_version: str = Field(default="template-aplicacao-v1", max_length=50)


class RelatorioCreate(RelatorioBase):
    pass


class RelatorioUpdate(BaseModel):
    numero_ata: str | None = Field(default=None, max_length=50)
    data_referencia: date | None = None
    titulo: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=50)
    report_json: dict[str, Any] | None = None
    html_path: str | None = None
    template_version: str | None = Field(default=None, max_length=50)


class RelatorioRead(RelatorioBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class RelatorioEtapaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    relatorio_id: int
    obra_id: int
    etapa_numero: int
    etapa_nome: str
    nome_output: str | None = None
    prompt_version: str | None = None
    status: str
    erro: str | None = None
    modelo_usado: str | None = None
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    created_at: datetime
    updated_at: datetime


class RelatorioDetalhe(RelatorioRead):
    etapas: list[RelatorioEtapaRead] = Field(default_factory=list)
