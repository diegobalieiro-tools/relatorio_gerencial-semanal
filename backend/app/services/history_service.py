from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.normalizados import (
    AlertaQualidade,
    Deliberacao,
    HistoricoItemStatus,
    ItemAcompanhamento,
    Pendencia,
    PlanoAcao,
    PontoCritico,
    ReprogramacaoPrazo,
)
from app.models.relatorio import RelatorioSemanal
from app.services.normalization_service import compact_json, normalizar_status


def _serialize(obj: Any) -> Any:
    if isinstance(obj, (date,)):
        return obj.isoformat()
    return obj


def _row_dict(row: Any, fields: list[str]) -> dict[str, Any]:
    return {field: _serialize(getattr(row, field, None)) for field in fields}


def build_resumo_historico_normalizado(db: Session, obra_id: int, limit: int = 30) -> dict[str, Any]:
    pendencias = db.scalars(
        select(Pendencia)
        .where(Pendencia.obra_id == obra_id)
        .order_by(desc(Pendencia.created_at))
        .limit(limit)
    ).all()

    pontos = db.scalars(
        select(PontoCritico)
        .where(PontoCritico.obra_id == obra_id)
        .order_by(desc(PontoCritico.created_at))
        .limit(limit)
    ).all()

    itens = db.scalars(
        select(ItemAcompanhamento)
        .where(ItemAcompanhamento.obra_id == obra_id)
        .order_by(desc(ItemAcompanhamento.created_at))
        .limit(limit)
    ).all()

    reprogramacoes = db.scalars(
        select(ReprogramacaoPrazo)
        .where(ReprogramacaoPrazo.obra_id == obra_id)
        .order_by(desc(ReprogramacaoPrazo.created_at))
        .limit(limit)
    ).all()

    plano = db.scalars(
        select(PlanoAcao)
        .where(PlanoAcao.obra_id == obra_id)
        .order_by(desc(PlanoAcao.created_at))
        .limit(limit)
    ).all()

    deliberacoes = db.scalars(
        select(Deliberacao)
        .where(Deliberacao.obra_id == obra_id)
        .order_by(desc(Deliberacao.created_at))
        .limit(limit)
    ).all()

    alertas = db.scalars(
        select(AlertaQualidade)
        .where(AlertaQualidade.obra_id == obra_id)
        .order_by(desc(AlertaQualidade.created_at))
        .limit(limit)
    ).all()

    ultimo_relatorio = db.scalars(
        select(RelatorioSemanal)
        .where(RelatorioSemanal.obra_id == obra_id, RelatorioSemanal.report_json.is_not(None))
        .order_by(desc(RelatorioSemanal.data_referencia))
        .limit(1)
    ).first()

    resumo = {
        "pendencias_abertas": [
            _row_dict(p, ["id", "titulo", "criticidade", "responsavel", "prazo", "impacto", "status", "origem"])
            for p in pendencias
            if normalizar_status(p.status) != "concluido"
        ],
        "pontos_criticos_recentes": [
            _row_dict(p, ["id", "titulo", "nivel", "responsavel", "prazo", "status", "impacto_direto"])
            for p in pontos
        ],
        "itens_em_andamento_ou_abertos": [
            _row_dict(i, ["id", "titulo", "categoria", "status", "criticidade", "responsavel", "prazo_vigente", "hash_item", "item_recorrente"])
            for i in itens
            if normalizar_status(i.status) != "concluido"
        ],
        "ultimas_reprogramacoes": [
            _row_dict(r, ["id", "prazo_anterior", "prazo_novo", "motivo_reprogramacao", "responsavel", "impacto", "fonte"])
            for r in reprogramacoes
        ],
        "plano_acao_aberto": [
            _row_dict(p, ["id", "titulo", "prioridade", "responsavel", "prazo", "status", "resultado_esperado"])
            for p in plano
            if normalizar_status(p.status) != "concluido"
        ],
        "deliberacoes_a_acompanhar": [
            _row_dict(d, ["id", "titulo", "tipo", "responsavel", "prazo", "decisao", "fonte"])
            for d in deliberacoes
        ],
        "alertas_qualidade_relevantes": [
            _row_dict(a, ["id", "tipo", "descricao", "fonte", "acao_recomendada"])
            for a in alertas
        ],
        "ultimo_report_json_resumido": compact_json(ultimo_relatorio.report_json if ultimo_relatorio else {}),
        "contadores": {
            "relatorios_gerados": db.scalar(select(func.count(RelatorioSemanal.id)).where(RelatorioSemanal.obra_id == obra_id)) or 0,
            "pendencias_registradas": len(pendencias),
            "pontos_criticos_registrados": len(pontos),
            "itens_acompanhamento": len(itens),
            "reprogramacoes": len(reprogramacoes),
        },
    }
    return resumo


def get_historico_pendencias(db: Session, obra_id: int) -> list[dict[str, Any]]:
    rows = db.scalars(select(Pendencia).where(Pendencia.obra_id == obra_id).order_by(desc(Pendencia.created_at))).all()
    return [_row_dict(r, ["id", "relatorio_id", "titulo", "descricao", "criticidade", "responsavel", "prazo", "impacto", "status", "origem"]) for r in rows]


def get_historico_pontos_criticos(db: Session, obra_id: int) -> list[dict[str, Any]]:
    rows = db.scalars(select(PontoCritico).where(PontoCritico.obra_id == obra_id).order_by(desc(PontoCritico.created_at))).all()
    return [_row_dict(r, ["id", "relatorio_id", "ordem", "titulo", "nivel", "responsavel", "prazo", "status", "impacto_direto", "acao_obrigatoria"]) for r in rows]


def get_historico_reprogramacoes(db: Session, obra_id: int) -> list[dict[str, Any]]:
    rows = db.scalars(select(ReprogramacaoPrazo).where(ReprogramacaoPrazo.obra_id == obra_id).order_by(desc(ReprogramacaoPrazo.created_at))).all()
    return [_row_dict(r, ["id", "item_acompanhamento_id", "relatorio_id", "prazo_anterior", "prazo_novo", "motivo_reprogramacao", "responsavel", "impacto", "fonte"]) for r in rows]


def get_historico_itens(db: Session, obra_id: int) -> list[dict[str, Any]]:
    rows = db.scalars(select(ItemAcompanhamento).where(ItemAcompanhamento.obra_id == obra_id).order_by(desc(ItemAcompanhamento.created_at))).all()
    return [_row_dict(r, ["id", "relatorio_id", "titulo", "categoria", "status", "criticidade", "responsavel", "empresa_responsavel", "prazo_original", "prazo_anterior", "prazo_vigente", "hash_item", "item_recorrente"]) for r in rows]


def get_linha_tempo_item(db: Session, obra_id: int, item_id: int) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(HistoricoItemStatus)
        .where(HistoricoItemStatus.obra_id == obra_id, HistoricoItemStatus.item_acompanhamento_id == item_id)
        .order_by(HistoricoItemStatus.created_at)
    ).all()
    return [_row_dict(r, ["id", "relatorio_id", "status_anterior", "status_atual", "criticidade_anterior", "criticidade_atual", "prazo_anterior", "prazo_atual", "comentario_evolucao", "created_at"]) for r in rows]
