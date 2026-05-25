from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Obra(Base):
    __tablename__ = "obras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    nome: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cliente: Mapped[str] = mapped_column(String(255), nullable=False)
    gerenciadora: Mapped[str] = mapped_column(String(255), nullable=False, default="TOOLS")
    executora: Mapped[str] = mapped_column(String(255), nullable=False)

    engenheiro_responsavel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prazo_contratual: Mapped[date | None] = mapped_column(Date, nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)

    ano_vigente: Mapped[int | None] = mapped_column(Integer, nullable=True)

    dicionario_tecnico_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    relatorios = relationship(
        "RelatorioSemanal",
        back_populates="obra",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
