"""create initial cvp semanal tables

Revision ID: 20260525_0001
Revises:
Create Date: 2026-05-25 00:01:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260525_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "obras",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("cliente", sa.String(length=255), nullable=False),
        sa.Column("gerenciadora", sa.String(length=255), nullable=False, server_default="TOOLS"),
        sa.Column("executora", sa.String(length=255), nullable=False),
        sa.Column("engenheiro_responsavel", sa.String(length=255), nullable=True),
        sa.Column("prazo_contratual", sa.Date(), nullable=True),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("ano_vigente", sa.Integer(), nullable=True),
        sa.Column("dicionario_tecnico_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_obras_id", "obras", ["id"])
    op.create_index("ix_obras_nome", "obras", ["nome"])

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("etapa", sa.Integer(), nullable=False),
        sa.Column("versao", sa.String(length=80), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_prompt_versions_id", "prompt_versions", ["id"])
    op.create_index("ix_prompt_versions_etapa", "prompt_versions", ["etapa"])

    op.create_table(
        "relatorios_semanais",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=False),
        sa.Column("numero_ata", sa.String(length=50), nullable=True),
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.Column("titulo", sa.String(length=255), nullable=False, server_default="Relatório Semanal de Obra"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="rascunho"),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("html_path", sa.Text(), nullable=True),
        sa.Column("template_version", sa.String(length=50), nullable=False, server_default="template-aplicacao-v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_relatorios_semanais_id", "relatorios_semanais", ["id"])
    op.create_index("ix_relatorios_semanais_obra_id", "relatorios_semanais", ["obra_id"])
    op.create_index("ix_relatorios_semanais_numero_ata", "relatorios_semanais", ["numero_ata"])
    op.create_index("ix_relatorios_semanais_data_referencia", "relatorios_semanais", ["data_referencia"])
    op.create_index("ix_relatorios_semanais_status", "relatorios_semanais", ["status"])

    op.create_table(
        "relatorio_arquivos",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("relatorio_id", sa.Integer(), nullable=False),
        sa.Column("nome_arquivo", sa.String(length=500), nullable=False),
        sa.Column("tipo_arquivo", sa.String(length=120), nullable=True),
        sa.Column("extensao", sa.String(length=20), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("tamanho_bytes", sa.BigInteger(), nullable=True),
        sa.Column("hash_arquivo", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["relatorio_id"], ["relatorios_semanais.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_relatorio_arquivos_id", "relatorio_arquivos", ["id"])
    op.create_index("ix_relatorio_arquivos_relatorio_id", "relatorio_arquivos", ["relatorio_id"])
    op.create_index("ix_relatorio_arquivos_hash_arquivo", "relatorio_arquivos", ["hash_arquivo"])

    op.create_table(
        "relatorio_etapas",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("relatorio_id", sa.Integer(), nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=False),
        sa.Column("etapa_numero", sa.Integer(), nullable=False),
        sa.Column("etapa_nome", sa.String(length=150), nullable=False),
        sa.Column("nome_output", sa.String(length=500), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pendente"),
        sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("modelo_usado", sa.String(length=120), nullable=True),
        sa.Column("tokens_entrada", sa.Integer(), nullable=True),
        sa.Column("tokens_saida", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["relatorio_id"], ["relatorios_semanais.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("relatorio_id", "etapa_numero", name="uq_relatorio_etapa_numero"),
    )
    op.create_index("ix_relatorio_etapas_id", "relatorio_etapas", ["id"])
    op.create_index("ix_relatorio_etapas_relatorio_id", "relatorio_etapas", ["relatorio_id"])
    op.create_index("ix_relatorio_etapas_obra_id", "relatorio_etapas", ["obra_id"])

    op.create_table(
        "pontos_criticos",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("relatorio_id", sa.Integer(), nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=True),
        sa.Column("titulo", sa.String(length=500), nullable=False),
        sa.Column("nivel", sa.String(length=50), nullable=True),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("impacto_direto", sa.Text(), nullable=True),
        sa.Column("acao_obrigatoria", sa.Text(), nullable=True),
        sa.Column("responsavel", sa.String(length=255), nullable=True),
        sa.Column("prazo", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["relatorio_id"], ["relatorios_semanais.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_pontos_criticos_id", "pontos_criticos", ["id"])
    op.create_index("ix_pontos_criticos_relatorio_id", "pontos_criticos", ["relatorio_id"])
    op.create_index("ix_pontos_criticos_obra_id", "pontos_criticos", ["obra_id"])

    op.create_table(
        "pendencias",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("relatorio_id", sa.Integer(), nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=500), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("criticidade", sa.String(length=50), nullable=True),
        sa.Column("responsavel", sa.String(length=255), nullable=True),
        sa.Column("tipo_responsavel", sa.String(length=80), nullable=True),
        sa.Column("prazo", sa.Date(), nullable=True),
        sa.Column("impacto", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=True),
        sa.Column("origem", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["relatorio_id"], ["relatorios_semanais.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_pendencias_id", "pendencias", ["id"])
    op.create_index("ix_pendencias_relatorio_id", "pendencias", ["relatorio_id"])
    op.create_index("ix_pendencias_obra_id", "pendencias", ["obra_id"])

    op.create_table(
        "plano_acao",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("relatorio_id", sa.Integer(), nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=500), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("prioridade", sa.String(length=50), nullable=True),
        sa.Column("responsavel", sa.String(length=255), nullable=True),
        sa.Column("prazo", sa.Date(), nullable=True),
        sa.Column("resultado_esperado", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["relatorio_id"], ["relatorios_semanais.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_plano_acao_id", "plano_acao", ["id"])
    op.create_index("ix_plano_acao_relatorio_id", "plano_acao", ["relatorio_id"])
    op.create_index("ix_plano_acao_obra_id", "plano_acao", ["obra_id"])

    op.create_table(
        "deliberacoes",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("relatorio_id", sa.Integer(), nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=500), nullable=False),
        sa.Column("tipo", sa.String(length=80), nullable=True),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("decisao", sa.Text(), nullable=True),
        sa.Column("responsavel", sa.String(length=255), nullable=True),
        sa.Column("prazo", sa.Date(), nullable=True),
        sa.Column("fonte", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["relatorio_id"], ["relatorios_semanais.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_deliberacoes_id", "deliberacoes", ["id"])
    op.create_index("ix_deliberacoes_relatorio_id", "deliberacoes", ["relatorio_id"])
    op.create_index("ix_deliberacoes_obra_id", "deliberacoes", ["obra_id"])

    op.create_table(
        "cronograma_itens",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("relatorio_id", sa.Integer(), nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=False),
        sa.Column("grupo", sa.String(length=255), nullable=True),
        sa.Column("frente", sa.String(length=255), nullable=True),
        sa.Column("responsavel", sa.String(length=255), nullable=True),
        sa.Column("inicio", sa.Date(), nullable=True),
        sa.Column("termino", sa.Date(), nullable=True),
        sa.Column("avanco_percentual", sa.Numeric(8, 2), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["relatorio_id"], ["relatorios_semanais.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_cronograma_itens_id", "cronograma_itens", ["id"])
    op.create_index("ix_cronograma_itens_relatorio_id", "cronograma_itens", ["relatorio_id"])
    op.create_index("ix_cronograma_itens_obra_id", "cronograma_itens", ["obra_id"])

    op.create_table(
        "alertas_qualidade",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("relatorio_id", sa.Integer(), nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=80), nullable=True),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("fonte", sa.String(length=255), nullable=True),
        sa.Column("acao_recomendada", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["relatorio_id"], ["relatorios_semanais.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_alertas_qualidade_id", "alertas_qualidade", ["id"])
    op.create_index("ix_alertas_qualidade_relatorio_id", "alertas_qualidade", ["relatorio_id"])
    op.create_index("ix_alertas_qualidade_obra_id", "alertas_qualidade", ["obra_id"])

    op.create_table(
        "itens_acompanhamento",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=False),
        sa.Column("relatorio_id", sa.Integer(), nullable=True),
        sa.Column("titulo", sa.String(length=500), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("categoria", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=True),
        sa.Column("criticidade", sa.String(length=50), nullable=True),
        sa.Column("responsavel", sa.String(length=255), nullable=True),
        sa.Column("empresa_responsavel", sa.String(length=255), nullable=True),
        sa.Column("prazo_original", sa.Date(), nullable=True),
        sa.Column("prazo_anterior", sa.Date(), nullable=True),
        sa.Column("prazo_vigente", sa.Date(), nullable=True),
        sa.Column("data_abertura", sa.Date(), nullable=True),
        sa.Column("data_ultima_atualizacao", sa.Date(), nullable=True),
        sa.Column("fonte", sa.String(length=255), nullable=True),
        sa.Column("evidencia", sa.Text(), nullable=True),
        sa.Column("hash_item", sa.String(length=128), nullable=False),
        sa.Column("item_recorrente", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["relatorio_id"], ["relatorios_semanais.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_itens_acompanhamento_id", "itens_acompanhamento", ["id"])
    op.create_index("ix_itens_acompanhamento_obra_id", "itens_acompanhamento", ["obra_id"])
    op.create_index("ix_itens_acompanhamento_relatorio_id", "itens_acompanhamento", ["relatorio_id"])
    op.create_index("ix_itens_acompanhamento_hash_item", "itens_acompanhamento", ["hash_item"])
    op.create_index("ix_itens_acompanhamento_obra_hash", "itens_acompanhamento", ["obra_id", "hash_item"])

    op.create_table(
        "historico_item_status",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=False),
        sa.Column("item_acompanhamento_id", sa.Integer(), nullable=False),
        sa.Column("relatorio_id", sa.Integer(), nullable=False),
        sa.Column("status_anterior", sa.String(length=80), nullable=True),
        sa.Column("status_atual", sa.String(length=80), nullable=True),
        sa.Column("criticidade_anterior", sa.String(length=50), nullable=True),
        sa.Column("criticidade_atual", sa.String(length=50), nullable=True),
        sa.Column("prazo_anterior", sa.Date(), nullable=True),
        sa.Column("prazo_atual", sa.Date(), nullable=True),
        sa.Column("comentario_evolucao", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["item_acompanhamento_id"], ["itens_acompanhamento.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["relatorio_id"], ["relatorios_semanais.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_historico_item_status_id", "historico_item_status", ["id"])
    op.create_index("ix_historico_item_status_obra_id", "historico_item_status", ["obra_id"])
    op.create_index("ix_historico_item_status_item_acompanhamento_id", "historico_item_status", ["item_acompanhamento_id"])
    op.create_index("ix_historico_item_status_relatorio_id", "historico_item_status", ["relatorio_id"])

    op.create_table(
        "reprogramacoes_prazo",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("obra_id", sa.Integer(), nullable=False),
        sa.Column("item_acompanhamento_id", sa.Integer(), nullable=False),
        sa.Column("relatorio_id", sa.Integer(), nullable=False),
        sa.Column("prazo_anterior", sa.Date(), nullable=True),
        sa.Column("prazo_novo", sa.Date(), nullable=True),
        sa.Column("motivo_reprogramacao", sa.Text(), nullable=True),
        sa.Column("responsavel", sa.String(length=255), nullable=True),
        sa.Column("impacto", sa.Text(), nullable=True),
        sa.Column("fonte", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["item_acompanhamento_id"], ["itens_acompanhamento.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["obra_id"], ["obras.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["relatorio_id"], ["relatorios_semanais.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_reprogramacoes_prazo_id", "reprogramacoes_prazo", ["id"])
    op.create_index("ix_reprogramacoes_prazo_obra_id", "reprogramacoes_prazo", ["obra_id"])
    op.create_index("ix_reprogramacoes_prazo_item_acompanhamento_id", "reprogramacoes_prazo", ["item_acompanhamento_id"])
    op.create_index("ix_reprogramacoes_prazo_relatorio_id", "reprogramacoes_prazo", ["relatorio_id"])


def downgrade() -> None:
    op.drop_index("ix_reprogramacoes_prazo_relatorio_id", table_name="reprogramacoes_prazo")
    op.drop_index("ix_reprogramacoes_prazo_item_acompanhamento_id", table_name="reprogramacoes_prazo")
    op.drop_index("ix_reprogramacoes_prazo_obra_id", table_name="reprogramacoes_prazo")
    op.drop_index("ix_reprogramacoes_prazo_id", table_name="reprogramacoes_prazo")
    op.drop_table("reprogramacoes_prazo")

    op.drop_index("ix_historico_item_status_relatorio_id", table_name="historico_item_status")
    op.drop_index("ix_historico_item_status_item_acompanhamento_id", table_name="historico_item_status")
    op.drop_index("ix_historico_item_status_obra_id", table_name="historico_item_status")
    op.drop_index("ix_historico_item_status_id", table_name="historico_item_status")
    op.drop_table("historico_item_status")

    op.drop_index("ix_itens_acompanhamento_obra_hash", table_name="itens_acompanhamento")
    op.drop_index("ix_itens_acompanhamento_hash_item", table_name="itens_acompanhamento")
    op.drop_index("ix_itens_acompanhamento_relatorio_id", table_name="itens_acompanhamento")
    op.drop_index("ix_itens_acompanhamento_obra_id", table_name="itens_acompanhamento")
    op.drop_index("ix_itens_acompanhamento_id", table_name="itens_acompanhamento")
    op.drop_table("itens_acompanhamento")

    op.drop_index("ix_alertas_qualidade_obra_id", table_name="alertas_qualidade")
    op.drop_index("ix_alertas_qualidade_relatorio_id", table_name="alertas_qualidade")
    op.drop_index("ix_alertas_qualidade_id", table_name="alertas_qualidade")
    op.drop_table("alertas_qualidade")

    op.drop_index("ix_cronograma_itens_obra_id", table_name="cronograma_itens")
    op.drop_index("ix_cronograma_itens_relatorio_id", table_name="cronograma_itens")
    op.drop_index("ix_cronograma_itens_id", table_name="cronograma_itens")
    op.drop_table("cronograma_itens")

    op.drop_index("ix_deliberacoes_obra_id", table_name="deliberacoes")
    op.drop_index("ix_deliberacoes_relatorio_id", table_name="deliberacoes")
    op.drop_index("ix_deliberacoes_id", table_name="deliberacoes")
    op.drop_table("deliberacoes")

    op.drop_index("ix_plano_acao_obra_id", table_name="plano_acao")
    op.drop_index("ix_plano_acao_relatorio_id", table_name="plano_acao")
    op.drop_index("ix_plano_acao_id", table_name="plano_acao")
    op.drop_table("plano_acao")

    op.drop_index("ix_pendencias_obra_id", table_name="pendencias")
    op.drop_index("ix_pendencias_relatorio_id", table_name="pendencias")
    op.drop_index("ix_pendencias_id", table_name="pendencias")
    op.drop_table("pendencias")

    op.drop_index("ix_pontos_criticos_obra_id", table_name="pontos_criticos")
    op.drop_index("ix_pontos_criticos_relatorio_id", table_name="pontos_criticos")
    op.drop_index("ix_pontos_criticos_id", table_name="pontos_criticos")
    op.drop_table("pontos_criticos")

    op.drop_index("ix_relatorio_etapas_obra_id", table_name="relatorio_etapas")
    op.drop_index("ix_relatorio_etapas_relatorio_id", table_name="relatorio_etapas")
    op.drop_index("ix_relatorio_etapas_id", table_name="relatorio_etapas")
    op.drop_table("relatorio_etapas")

    op.drop_index("ix_relatorio_arquivos_hash_arquivo", table_name="relatorio_arquivos")
    op.drop_index("ix_relatorio_arquivos_relatorio_id", table_name="relatorio_arquivos")
    op.drop_index("ix_relatorio_arquivos_id", table_name="relatorio_arquivos")
    op.drop_table("relatorio_arquivos")

    op.drop_index("ix_relatorios_semanais_status", table_name="relatorios_semanais")
    op.drop_index("ix_relatorios_semanais_data_referencia", table_name="relatorios_semanais")
    op.drop_index("ix_relatorios_semanais_numero_ata", table_name="relatorios_semanais")
    op.drop_index("ix_relatorios_semanais_obra_id", table_name="relatorios_semanais")
    op.drop_index("ix_relatorios_semanais_id", table_name="relatorios_semanais")
    op.drop_table("relatorios_semanais")

    op.drop_index("ix_prompt_versions_etapa", table_name="prompt_versions")
    op.drop_index("ix_prompt_versions_id", table_name="prompt_versions")
    op.drop_table("prompt_versions")

    op.drop_index("ix_obras_nome", table_name="obras")
    op.drop_index("ix_obras_id", table_name="obras")
    op.drop_table("obras")
