from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RelatorioSemanal(Base):
    __tablename__ = "relatorios_semanais"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    obra_id: Mapped[int] = mapped_column(
        ForeignKey("obras.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    numero_ata: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    data_referencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    titulo: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="Relatório Semanal de Obra",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="rascunho",
        index=True,
    )

    report_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    html_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_version: Mapped[str] = mapped_column(String(50), nullable=False, default="template-aplicacao-v1")

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

    obra = relationship("Obra", back_populates="relatorios")
    arquivos = relationship(
        "RelatorioArquivo",
        back_populates="relatorio",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    etapas = relationship(
        "RelatorioEtapa",
        back_populates="relatorio",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class RelatorioArquivo(Base):
    __tablename__ = "relatorio_arquivos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    relatorio_id: Mapped[int] = mapped_column(
        ForeignKey("relatorios_semanais.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    nome_arquivo: Mapped[str] = mapped_column(String(500), nullable=False)
    tipo_arquivo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    extensao: Mapped[str | None] = mapped_column(String(20), nullable=True)

    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    tamanho_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    hash_arquivo: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    relatorio = relationship("RelatorioSemanal", back_populates="arquivos")


class RelatorioEtapa(Base):
    __tablename__ = "relatorio_etapas"

    __table_args__ = (
        UniqueConstraint("relatorio_id", "etapa_numero", name="uq_relatorio_etapa_numero"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    relatorio_id: Mapped[int] = mapped_column(
        ForeignKey("relatorios_semanais.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    obra_id: Mapped[int] = mapped_column(
        ForeignKey("obras.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    etapa_numero: Mapped[int] = mapped_column(Integer, nullable=False)
    etapa_nome: Mapped[str] = mapped_column(String(150), nullable=False)

    nome_output: Mapped[str | None] = mapped_column(String(500), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pendente")

    input_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    erro: Mapped[str | None] = mapped_column(Text, nullable=True)
    modelo_usado: Mapped[str | None] = mapped_column(String(120), nullable=True)

    tokens_entrada: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_saida: Mapped[int | None] = mapped_column(Integer, nullable=True)

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

    relatorio = relationship("RelatorioSemanal", back_populates="etapas")
