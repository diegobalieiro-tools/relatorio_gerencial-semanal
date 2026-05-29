from __future__ import annotations

from datetime import date
import re
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



def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _norm_key(value: Any) -> str:
    text = _clean_text(value).lower()
    replacements = str.maketrans("áàãâäéèêëíìîïóòõôöúùûüç", "aaaaaeeeeiiiiooooouuuuc")
    text = text.translate(replacements)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _date_to_iso(value: Any) -> str:
    """Normaliza datas do report_json para ISO, para o frontend calcular atraso."""
    text = _clean_text(value)
    if not text or text.lower() in {"nao informado", "não informado", "nao informada", "não informada", "-", "—"}:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", text)
    if match:
        day, month, year = match.groups()
        if len(year) == 2:
            year = f"20{year}"
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return text


def _tag_value(tags: list[Any], prefix: str) -> str:
    prefix_norm = _norm_key(prefix)
    for tag in tags:
        text = _clean_text(tag)
        if _norm_key(text).startswith(prefix_norm):
            parts = re.split(r":|·|-", text, maxsplit=1)
            if len(parts) > 1:
                return _clean_text(parts[1])
    return ""


def _item_status_from_report(item: dict[str, Any], default_andamento: bool = False) -> str:
    status = _clean_text(item.get("status") or item.get("type") or item.get("tipo"))
    tags_text = " ".join(_clean_text(t) for t in _as_list(item.get("tags")))
    combined = _norm_key(f"{status} {tags_text}")
    if "concluid" in combined or "resolvid" in combined:
        return "Concluído"
    if "inform" in combined:
        return "Informação"
    if "bloque" in combined:
        return "Bloqueante"
    if "atras" in combined:
        return "Atrasada"
    if "pend" in combined:
        return "Pendente"
    if "andamento" in combined or default_andamento:
        return "Em andamento"
    return status or "Em andamento"


def _report_json_candidates(report_json: dict[str, Any]) -> list[tuple[str, dict[str, Any], bool]]:
    """Lê a fonte mais fiel da última versão do relatório.

    A aba 01 do HTML é montada em `criticalPoints` e, por regra atual do
    relatório, contém todos os itens com Status = Em andamento. Por isso ela é
    a fonte principal da tela da obra. Demais estruturas entram apenas como
    fallback, para versões antigas do JSON.
    """
    candidates: list[tuple[str, dict[str, Any], bool]] = []

    for item in _as_list(report_json.get("criticalPoints")):
        if isinstance(item, dict):
            candidates.append(("criticalPoints", item, True))

    sections = _as_dict(report_json.get("sections"))
    pontos_section = _as_dict(sections.get("pontosCriticos"))
    for item in _as_list(pontos_section.get("items")):
        if isinstance(item, dict):
            candidates.append(("sections.pontosCriticos.items", item, True))

    pend_section = _as_dict(sections.get("pendencias"))
    for item in _as_list(pend_section.get("items")):
        if isinstance(item, dict):
            candidates.append(("sections.pendencias.items", item, False))

    for key in ["atividades", "itens_acompanhamento"]:
        for item in _as_list(report_json.get(key)):
            if isinstance(item, dict):
                candidates.append((key, item, False))

    persistencia = _as_dict(report_json.get("dados_para_persistencia"))
    for item in _as_list(persistencia.get("itens_acompanhamento")):
        if isinstance(item, dict):
            candidates.append(("dados_para_persistencia.itens_acompanhamento", item, False))

    # Fallback menor: cronograma da ata atual. Não deve substituir a aba 01,
    # mas ajuda relatórios antigos que ainda não possuem criticalPoints.
    for item in _as_list(report_json.get("schedule")):
        if isinstance(item, dict):
            candidates.append(("schedule", item, False))
    cronograma = _as_dict(sections.get("cronograma"))
    for item in _as_list(cronograma.get("rows")):
        if isinstance(item, dict):
            candidates.append(("sections.cronograma.rows", item, False))

    return candidates


def _extract_pendencias_from_report_json(relatorio: RelatorioSemanal) -> list[dict[str, Any]]:
    """Extrai todas as pendências em andamento do report_json do último relatório.

    Isso evita a tela da obra depender apenas da tabela normalizada
    `itens_acompanhamento`, que pode ficar incompleta em relatórios antigos ou
    em reprocessamentos. A fonte de verdade visual passa a ser o último HTML/JSON
    gerado.
    """
    report_json = _as_dict(relatorio.report_json)
    if not report_json:
        return []

    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    referencia = _date_to_iso(getattr(relatorio, "data_referencia", None))

    for idx, (source, item, default_andamento) in enumerate(_report_json_candidates(report_json), start=1):
        status = _item_status_from_report(item, default_andamento=default_andamento)
        if normalizar_status(status) != "andamento":
            continue

        tags = _as_list(item.get("tags"))
        titulo = _clean_text(
            item.get("titulo")
            or item.get("title")
            or item.get("front")
            or item.get("frente")
            or item.get("nome")
        )
        if not titulo:
            continue

        key = _norm_key(titulo)
        if key in seen:
            continue
        seen.add(key)

        prazo = (
            item.get("prazo_vigente")
            or item.get("prazo")
            or item.get("deadline")
            or item.get("end")
            or item.get("termino")
            or _tag_value(tags, "Prazo")
        )
        inicio = (
            item.get("data_abertura")
            or item.get("data_inicio")
            or item.get("data_item")
            or item.get("start")
            or item.get("inicio")
            or referencia
        )
        responsavel = (
            item.get("responsavel")
            or item.get("responsible")
            or item.get("empresa_responsavel")
            or item.get("resp")
            or _tag_value(tags, "Responsável")
        )
        criticidade = item.get("criticidade") or item.get("level") or item.get("nivel") or item.get("priority") or ""
        descricao = item.get("descricao") or item.get("description") or item.get("body") or item.get("observation") or item.get("observacao") or ""

        output.append(
            {
                "id": _clean_text(item.get("id") or f"json-{relatorio.id}-{idx}"),
                "relatorio_id": relatorio.id,
                "titulo": titulo,
                "descricao": _clean_text(descricao),
                "categoria": _clean_text(item.get("categoria") or source),
                "status": "Em andamento",
                "criticidade": _clean_text(criticidade),
                "responsavel": _clean_text(responsavel),
                "empresa_responsavel": _clean_text(item.get("empresa_responsavel")),
                "prazo_original": _date_to_iso(item.get("prazo_original")),
                "prazo_anterior": _date_to_iso(item.get("prazo_anterior")),
                "prazo_vigente": _date_to_iso(prazo),
                "data_abertura": _date_to_iso(inicio),
                "data_ultima_atualizacao": referencia,
                "created_at": referencia,
            }
        )

    return output


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
    """Retorna as pendências ativas do último relatório válido da obra.

    A tela da obra deve refletir o estado mais recente consolidado, não o
    histórico acumulado de todos os relatórios. Por isso a fonte principal é a
    tabela de itens de acompanhamento do último relatório com report_json,
    filtrando apenas itens ainda em andamento.
    """

    ultimo_relatorio = db.scalars(
        select(RelatorioSemanal)
        .where(
            RelatorioSemanal.obra_id == obra_id,
            RelatorioSemanal.report_json.is_not(None),
            RelatorioSemanal.status != "erro",
        )
        .order_by(desc(RelatorioSemanal.data_referencia), desc(RelatorioSemanal.id))
        .limit(1)
    ).first()

    if not ultimo_relatorio:
        return []

    pendencias_report_json = _extract_pendencias_from_report_json(ultimo_relatorio)
    if pendencias_report_json:
        return pendencias_report_json

    itens = db.scalars(
        select(ItemAcompanhamento)
        .where(
            ItemAcompanhamento.obra_id == obra_id,
            ItemAcompanhamento.relatorio_id == ultimo_relatorio.id,
        )
        .order_by(ItemAcompanhamento.id.asc())
    ).all()

    pendencias = [
        _row_dict(
            item,
            [
                "id",
                "relatorio_id",
                "titulo",
                "descricao",
                "categoria",
                "status",
                "criticidade",
                "responsavel",
                "empresa_responsavel",
                "prazo_original",
                "prazo_anterior",
                "prazo_vigente",
                "data_abertura",
                "data_ultima_atualizacao",
                "created_at",
            ],
        )
        for item in itens
        if normalizar_status(item.status) == "andamento"
    ]

    if pendencias:
        return pendencias

    # Fallback para relatórios antigos que ainda não popularam itens_acompanhamento.
    rows = db.scalars(
        select(Pendencia)
        .where(Pendencia.obra_id == obra_id, Pendencia.relatorio_id == ultimo_relatorio.id)
        .order_by(Pendencia.id.asc())
    ).all()
    return [
        _row_dict(r, ["id", "relatorio_id", "titulo", "descricao", "criticidade", "responsavel", "prazo", "impacto", "status", "origem", "created_at"])
        for r in rows
        if normalizar_status(r.status) in {"andamento", "pendente", "bloqueante"}
    ]


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
