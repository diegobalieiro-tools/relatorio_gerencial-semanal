from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ObraBase(BaseModel):
    nome: str = Field(min_length=1, max_length=255)
    cliente: str = Field(min_length=1, max_length=255)
    executora: str = Field(min_length=1, max_length=255)

    gerenciadora: str = Field(default="TOOLS", max_length=255)
    engenheiro_responsavel: str | None = Field(default=None, max_length=255)
    prazo_contratual: date | None = None
    ano_vigente: int | None = None
    observacoes: str | None = None
    dicionario_tecnico_json: dict[str, Any] = Field(default_factory=dict)


class ObraCreate(ObraBase):
    pass


class ObraUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=255)
    cliente: str | None = Field(default=None, min_length=1, max_length=255)
    executora: str | None = Field(default=None, min_length=1, max_length=255)

    gerenciadora: str | None = Field(default=None, max_length=255)
    engenheiro_responsavel: str | None = Field(default=None, max_length=255)
    prazo_contratual: date | None = None
    ano_vigente: int | None = None
    observacoes: str | None = None
    dicionario_tecnico_json: dict[str, Any] | None = None


class ObraRead(ObraBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ObraListItem(ObraRead):
    relatorios_count: int = 0
    ultimo_relatorio: date | None = None
