from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.normalizados import (
    AlertaQualidade,
    CronogramaItem,
    Deliberacao,
    HistoricoItemStatus,
    ItemAcompanhamento,
    Pendencia,
    PlanoAcao,
    PontoCritico,
    ReprogramacaoPrazo,
)
from app.services.normalization_service import gerar_hash_item, normalizar_criticidade, normalizar_status, safe_date, safe_text


@dataclass
class PersistenceResult:
    pontos_criticos: int = 0
    pendencias: int = 0
    plano_acao: int = 0
    deliberacoes: int = 0
    cronograma_itens: int = 0
    alertas_qualidade: int = 0
    itens_acompanhamento: int = 0
    historicos_status: int = 0
    reprogramacoes_prazo: int = 0

    def as_dict(self) -> dict[str, int]:
        return self.__dict__.copy()


def _delete_report_rows(db: Session, relatorio_id: int) -> None:
    for model in [
        PontoCritico,
        Pendencia,
        PlanoAcao,
        Deliberacao,
        CronogramaItem,
        AlertaQualidade,
        HistoricoItemStatus,
        ReprogramacaoPrazo,
    ]:
        db.query(model).filter(model.relatorio_id == relatorio_id).delete(synchronize_session=False)


def _latest_item_by_hash(db: Session, obra_id: int, hash_item: str) -> ItemAcompanhamento | None:
    return db.scalars(
        select(ItemAcompanhamento)
        .where(ItemAcompanhamento.obra_id == obra_id, ItemAcompanhamento.hash_item == hash_item)
        .order_by(desc(ItemAcompanhamento.created_at))
        .limit(1)
    ).first()


def persist_output_gpt2(
    db: Session,
    obra_id: int,
    relatorio_id: int,
    dados: dict[str, Any],
) -> PersistenceResult:
    result = PersistenceResult()
    _delete_report_rows(db, relatorio_id)

    for idx, item in enumerate(dados.get("pontos_criticos") or [], start=1):
        row = PontoCritico(
            relatorio_id=relatorio_id,
            obra_id=obra_id,
            ordem=item.get("ordem") or idx,
            titulo=safe_text(item.get("titulo")),
            nivel=normalizar_criticidade(item.get("nivel")),
            descricao=item.get("descricao_executiva") or item.get("descricao") or "",
            impacto_direto=item.get("impacto_direto") or "",
            acao_obrigatoria=item.get("acao_obrigatoria") or "",
            responsavel=item.get("responsavel") or "Indefinido",
            prazo=safe_date(item.get("prazo_limite") or item.get("prazo")),
            status=normalizar_status(item.get("status")) or "pendente",
            tags=item.get("tags") or [],
        )
        db.add(row)
        result.pontos_criticos += 1

    for item in dados.get("pendencias") or []:
        row = Pendencia(
            relatorio_id=relatorio_id,
            obra_id=obra_id,
            titulo=safe_text(item.get("titulo")),
            descricao=item.get("descricao") or "",
            criticidade=normalizar_criticidade(item.get("criticidade")),
            responsavel=item.get("responsavel_pendencia") or item.get("responsavel") or "Indefinido",
            tipo_responsavel=item.get("tipo_responsavel") or "Indefinido",
            prazo=safe_date(item.get("prazo")),
            impacto=item.get("impacto") or "",
            status=normalizar_status(item.get("status")) or "pendente",
            origem=item.get("fonte") or "GPT2",
        )
        db.add(row)
        result.pendencias += 1

    for item in dados.get("plano_acao") or []:
        row = PlanoAcao(
            relatorio_id=relatorio_id,
            obra_id=obra_id,
            titulo=safe_text(item.get("titulo")),
            descricao=item.get("descricao") or "",
            prioridade=item.get("prioridade") or "",
            responsavel=item.get("responsavel") or "Indefinido",
            prazo=safe_date(item.get("prazo")),
            resultado_esperado=item.get("resultado_esperado") or "",
            status=normalizar_status(item.get("status")) or "pendente",
        )
        db.add(row)
        result.plano_acao += 1

    for item in dados.get("deliberacoes") or []:
        responsaveis = item.get("responsaveis") or []
        responsavel = ", ".join(responsaveis) if isinstance(responsaveis, list) else safe_text(responsaveis)
        row = Deliberacao(
            relatorio_id=relatorio_id,
            obra_id=obra_id,
            titulo=safe_text(item.get("titulo")),
            tipo=item.get("tipo") or "",
            descricao=item.get("descricao") or "",
            decisao=item.get("decisao") or "",
            responsavel=responsavel or "Indefinido",
            prazo=safe_date(item.get("prazo")),
            fonte=item.get("fonte") or "GPT2",
        )
        db.add(row)
        result.deliberacoes += 1

    for item in dados.get("cronograma_executivo") or []:
        row = CronogramaItem(
            relatorio_id=relatorio_id,
            obra_id=obra_id,
            grupo=item.get("grupo") or "",
            frente=item.get("frente") or item.get("ambiente_ou_pacote") or "",
            responsavel=item.get("responsavel") or "Indefinido",
            inicio=safe_date(item.get("inicio")),
            termino=safe_date(item.get("termino") or item.get("prazo_reprogramado")),
            avanco_percentual=item.get("avanco_percentual"),
            status=normalizar_status(item.get("status")),
            observacao=item.get("observacao") or "",
        )
        db.add(row)
        result.cronograma_itens += 1

    for item in dados.get("alertas_qualidade") or []:
        row = AlertaQualidade(
            relatorio_id=relatorio_id,
            obra_id=obra_id,
            tipo=item.get("tipo") or "outro",
            descricao=safe_text(item.get("descricao")),
            fonte=item.get("fonte") or "GPT2",
            acao_recomendada=item.get("acao_recomendada") or "",
        )
        db.add(row)
        result.alertas_qualidade += 1

    dados_persistencia = dados.get("dados_para_persistencia") or {}
    itens = dados_persistencia.get("itens_acompanhamento") or dados.get("atividades") or []

    for item in itens:
        titulo = safe_text(item.get("titulo"))
        responsavel = item.get("responsavel") or item.get("responsavel_pendencia") or "Indefinido"
        hash_item = gerar_hash_item(obra_id, titulo, responsavel)
        existente = _latest_item_by_hash(db, obra_id, hash_item)

        status_anterior = existente.status if existente else None
        criticidade_anterior = existente.criticidade if existente else None
        prazo_anterior = existente.prazo_vigente if existente else safe_date(item.get("prazo_anterior"))
        prazo_atual = safe_date(item.get("prazo_vigente") or item.get("prazo") or item.get("prazo_atual"))

        if existente:
            existente.relatorio_id = relatorio_id
            existente.descricao = item.get("descricao") or existente.descricao
            existente.categoria = item.get("categoria") or existente.categoria
            existente.status = normalizar_status(item.get("status")) or existente.status
            existente.criticidade = normalizar_criticidade(item.get("criticidade")) or existente.criticidade
            existente.responsavel = responsavel
            existente.empresa_responsavel = item.get("empresa_responsavel") or existente.empresa_responsavel
            existente.prazo_anterior = prazo_anterior
            existente.prazo_vigente = prazo_atual
            existente.data_ultima_atualizacao = safe_date(item.get("data_ultima_atualizacao"))
            existente.fonte = item.get("fonte") or existente.fonte
            existente.evidencia = item.get("evidencia") or existente.evidencia
            existente.item_recorrente = True
            acompanhamento = existente
        else:
            acompanhamento = ItemAcompanhamento(
                obra_id=obra_id,
                relatorio_id=relatorio_id,
                titulo=titulo,
                descricao=item.get("descricao") or "",
                categoria=item.get("categoria") or "",
                status=normalizar_status(item.get("status")) or "pendente",
                criticidade=normalizar_criticidade(item.get("criticidade")),
                responsavel=responsavel,
                empresa_responsavel=item.get("empresa_responsavel") or "",
                prazo_original=safe_date(item.get("prazo_original")),
                prazo_anterior=prazo_anterior,
                prazo_vigente=prazo_atual,
                data_abertura=safe_date(item.get("data_abertura")),
                data_ultima_atualizacao=safe_date(item.get("data_ultima_atualizacao")),
                fonte=item.get("fonte") or "GPT2",
                evidencia=item.get("evidencia") or "",
                hash_item=hash_item,
                item_recorrente=bool(item.get("item_recorrente")) or False,
            )
            db.add(acompanhamento)
            db.flush()

        result.itens_acompanhamento += 1

        historico = HistoricoItemStatus(
            obra_id=obra_id,
            item_acompanhamento_id=acompanhamento.id,
            relatorio_id=relatorio_id,
            status_anterior=status_anterior,
            status_atual=acompanhamento.status,
            criticidade_anterior=criticidade_anterior,
            criticidade_atual=acompanhamento.criticidade,
            prazo_anterior=prazo_anterior,
            prazo_atual=prazo_atual,
            comentario_evolucao=item.get("historico_cronologico") or item.get("comentario_evolucao") or "",
        )
        db.add(historico)
        result.historicos_status += 1

        houve_reprogramacao = bool(item.get("houve_reprogramacao")) or (prazo_anterior and prazo_atual and prazo_anterior != prazo_atual)
        if houve_reprogramacao:
            db.add(
                ReprogramacaoPrazo(
                    obra_id=obra_id,
                    item_acompanhamento_id=acompanhamento.id,
                    relatorio_id=relatorio_id,
                    prazo_anterior=prazo_anterior,
                    prazo_novo=prazo_atual,
                    motivo_reprogramacao=item.get("motivo_reprogramacao") or "Alteração de prazo identificada entre relatórios.",
                    responsavel=responsavel,
                    impacto=item.get("impacto_na_obra") or item.get("impacto") or "",
                    fonte=item.get("fonte") or "GPT2",
                )
            )
            result.reprogramacoes_prazo += 1

    db.flush()
    return result
