from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PontoCritico(Base):
    __tablename__ = "pontos_criticos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    relatorio_id: Mapped[int] = mapped_column(ForeignKey("relatorios_semanais.id", ondelete="CASCADE"), index=True)
    obra_id: Mapped[int] = mapped_column(ForeignKey("obras.id", ondelete="CASCADE"), index=True)

    ordem: Mapped[int | None] = mapped_column(Integer, nullable=True)
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    nivel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)

    impacto_direto: Mapped[str | None] = mapped_column(Text, nullable=True)
    acao_obrigatoria: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsavel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prazo: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str | None] = mapped_column(String(80), nullable=True)

    tags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Pendencia(Base):
    __tablename__ = "pendencias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    relatorio_id: Mapped[int] = mapped_column(ForeignKey("relatorios_semanais.id", ondelete="CASCADE"), index=True)
    obra_id: Mapped[int] = mapped_column(ForeignKey("obras.id", ondelete="CASCADE"), index=True)

    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    criticidade: Mapped[str | None] = mapped_column(String(50), nullable=True)
    responsavel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tipo_responsavel: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prazo: Mapped[date | None] = mapped_column(Date, nullable=True)
    impacto: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    origem: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlanoAcao(Base):
    __tablename__ = "plano_acao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    relatorio_id: Mapped[int] = mapped_column(ForeignKey("relatorios_semanais.id", ondelete="CASCADE"), index=True)
    obra_id: Mapped[int] = mapped_column(ForeignKey("obras.id", ondelete="CASCADE"), index=True)

    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    prioridade: Mapped[str | None] = mapped_column(String(50), nullable=True)
    responsavel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prazo: Mapped[date | None] = mapped_column(Date, nullable=True)
    resultado_esperado: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(80), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Deliberacao(Base):
    __tablename__ = "deliberacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    relatorio_id: Mapped[int] = mapped_column(ForeignKey("relatorios_semanais.id", ondelete="CASCADE"), index=True)
    obra_id: Mapped[int] = mapped_column(ForeignKey("obras.id", ondelete="CASCADE"), index=True)

    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    tipo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    decisao: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsavel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prazo: Mapped[date | None] = mapped_column(Date, nullable=True)
    fonte: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CronogramaItem(Base):
    __tablename__ = "cronograma_itens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    relatorio_id: Mapped[int] = mapped_column(ForeignKey("relatorios_semanais.id", ondelete="CASCADE"), index=True)
    obra_id: Mapped[int] = mapped_column(ForeignKey("obras.id", ondelete="CASCADE"), index=True)

    grupo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    frente: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsavel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    termino: Mapped[date | None] = mapped_column(Date, nullable=True)
    avanco_percentual: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlertaQualidade(Base):
    __tablename__ = "alertas_qualidade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    relatorio_id: Mapped[int] = mapped_column(ForeignKey("relatorios_semanais.id", ondelete="CASCADE"), index=True)
    obra_id: Mapped[int] = mapped_column(ForeignKey("obras.id", ondelete="CASCADE"), index=True)

    tipo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    fonte: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acao_recomendada: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ItemAcompanhamento(Base):
    __tablename__ = "itens_acompanhamento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    obra_id: Mapped[int] = mapped_column(ForeignKey("obras.id", ondelete="CASCADE"), index=True)
    relatorio_id: Mapped[int | None] = mapped_column(ForeignKey("relatorios_semanais.id", ondelete="SET NULL"), index=True)

    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    categoria: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    criticidade: Mapped[str | None] = mapped_column(String(50), nullable=True)

    responsavel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    empresa_responsavel: Mapped[str | None] = mapped_column(String(255), nullable=True)

    prazo_original: Mapped[date | None] = mapped_column(Date, nullable=True)
    prazo_anterior: Mapped[date | None] = mapped_column(Date, nullable=True)
    prazo_vigente: Mapped[date | None] = mapped_column(Date, nullable=True)

    data_abertura: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_ultima_atualizacao: Mapped[date | None] = mapped_column(Date, nullable=True)

    fonte: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidencia: Mapped[str | None] = mapped_column(Text, nullable=True)

    hash_item: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    item_recorrente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HistoricoItemStatus(Base):
    __tablename__ = "historico_item_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    obra_id: Mapped[int] = mapped_column(ForeignKey("obras.id", ondelete="CASCADE"), index=True)
    item_acompanhamento_id: Mapped[int] = mapped_column(ForeignKey("itens_acompanhamento.id", ondelete="CASCADE"), index=True)
    relatorio_id: Mapped[int] = mapped_column(ForeignKey("relatorios_semanais.id", ondelete="CASCADE"), index=True)

    status_anterior: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status_atual: Mapped[str | None] = mapped_column(String(80), nullable=True)
    criticidade_anterior: Mapped[str | None] = mapped_column(String(50), nullable=True)
    criticidade_atual: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prazo_anterior: Mapped[date | None] = mapped_column(Date, nullable=True)
    prazo_atual: Mapped[date | None] = mapped_column(Date, nullable=True)
    comentario_evolucao: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReprogramacaoPrazo(Base):
    __tablename__ = "reprogramacoes_prazo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    obra_id: Mapped[int] = mapped_column(ForeignKey("obras.id", ondelete="CASCADE"), index=True)
    item_acompanhamento_id: Mapped[int] = mapped_column(ForeignKey("itens_acompanhamento.id", ondelete="CASCADE"), index=True)
    relatorio_id: Mapped[int] = mapped_column(ForeignKey("relatorios_semanais.id", ondelete="CASCADE"), index=True)

    prazo_anterior: Mapped[date | None] = mapped_column(Date, nullable=True)
    prazo_novo: Mapped[date | None] = mapped_column(Date, nullable=True)
    motivo_reprogramacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsavel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    impacto: Mapped[str | None] = mapped_column(Text, nullable=True)
    fonte: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
