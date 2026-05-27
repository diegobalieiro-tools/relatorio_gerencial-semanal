from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any

ACTIVE_STATUSES = {"Em andamento", "Atrasada", "Não iniciado", "Pendente", "Bloqueante"}
INFORMATIVE_STATUSES = {"Informativo"}
CONCLUDED_STATUSES = {"Concluído"}
DONE_STATUSES = CONCLUDED_STATUSES | INFORMATIVE_STATUSES


def _get(value: dict[str, Any], *keys: str, default: Any = "") -> Any:
    cursor: Any = value
    for key in keys:
        if not isinstance(cursor, dict):
            return default
        cursor = cursor.get(key)
    return cursor if cursor is not None else default


def _text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_id(index: int) -> str:
    return f"{index:02d}"


def _strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")


def _norm_key(value: Any) -> str:
    text = _strip_accents(str(value or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _item_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _text(item.get("numero_ata_origem")),
        _text(item.get("numero_item")),
        _norm_key(item.get("titulo")),
    )


def _to_iso_or_text(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%d/%m/%Y")
    text = str(value).strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return text


def _date_obj(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _status_text(item: dict[str, Any]) -> str:
    status = _text(item.get("status"), "Pendente")
    if "concl" in _norm_key(status):
        return "Concluído"
    if "inform" in _norm_key(status):
        return "Informativo"
    if "bloque" in _norm_key(status):
        return "Bloqueante"
    if "atras" in _norm_key(status):
        return "Atrasada"
    if "nao iniciado" in _norm_key(status):
        return "Não iniciado"
    if "andamento" in _norm_key(status):
        return "Em andamento"
    if "pendente" in _norm_key(status):
        return "Pendente"
    return status


def _is_active(item: dict[str, Any]) -> bool:
    return _status_text(item) in ACTIVE_STATUSES


def _is_informative(item: dict[str, Any]) -> bool:
    return _status_text(item) in INFORMATIVE_STATUSES or _text(item.get("tipo_registro")) == "informativo"


def _is_concluded(item: dict[str, Any]) -> bool:
    return _status_text(item) in CONCLUDED_STATUSES or _text(item.get("tipo_registro")) == "concluido"


def _section_label(item: dict[str, Any]) -> str:
    section = _text(item.get("secao"), "Ata")
    if "ata atual" in _norm_key(section):
        return "Itens Ata Atual"
    if "pendentes" in _norm_key(section):
        return "Itens Ata Anterior / Pendentes"
    if "concluidos" in _norm_key(section) or "informativos" in _norm_key(section):
        return "Concluídos / Informativos"
    return section


def _status_to_template(status: Any) -> tuple[str, str]:
    text = _norm_key(status)
    if "conclu" in text:
        return "concluido", "Concluído"
    if "inform" in text:
        return "informativo", "Informativo"
    if "bloque" in text:
        return "bloqueado", "Bloqueante"
    if "atras" in text:
        return "atrasado", "Atrasada"
    if "nao iniciado" in text:
        return "nao-iniciado", "Não iniciado"
    if "andamento" in text:
        return "andamento", "Em andamento"
    if "pend" in text:
        return "bloqueado", "Pendente"
    return "andamento", _text(status, "Em andamento")


def _normalize_level(value: Any, item: dict[str, Any] | None = None, data_ref: date | None = None) -> str:
    text = _norm_key(value)
    if "critic" in text or "bloque" in text:
        return "critico"
    if "alta" in text or "alto" in text:
        return "alto"
    if "media" in text or "moder" in text:
        return "moderado"
    if "baixo" in text or "baixa" in text:
        return "baixo"

    item = item or {}
    status = _norm_key(item.get("status"))
    title = _norm_key(item.get("titulo"))
    prazo = _date_obj(item.get("prazo_vigente") or item.get("prazo"))
    incidencia = int(item.get("incidencia_detectada") or 1)
    reprogramacoes = int(item.get("reprogramacoes_detectadas") or 0)

    if "bloque" in status:
        return "critico"
    if data_ref and prazo and prazo < data_ref and not (_is_concluded(item) or _is_informative(item)):
        return "critico" if incidencia >= 2 else "alto"
    if incidencia >= 4 or reprogramacoes >= 3:
        return "alto"
    if any(word in title for word in ["cronograma", "contratacao", "contrato", "demolicao", "projeto estrutural"]):
        return "alto" if incidencia >= 2 else "moderado"
    if "andamento" in status or "pendente" in status:
        return "moderado"
    return "baixo"


def _level_label(level: str) -> str:
    return {"critico": "Crítica", "alto": "Alta", "moderado": "Média", "baixo": "Baixa"}.get(level, "Média")


def _priority_label(level: str) -> str:
    return {"critico": "Crítico", "alto": "Alta", "moderado": "Média", "baixo": "Baixa"}.get(level, "Média")


def _extract_items(step1_data: dict[str, Any], step2_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Retorna itens consolidados sem duplicidade.

    Quando existe parser_ata_tools, ele vira a fonte principal para evitar alucinação
    do GPT. Os itens do GPT só entram se não houver nenhum item determinístico.
    """
    parser_items = _list(_get(step1_data, "parser_ata_tools", "itens_validados", default=[]))
    step1_items = _list(step1_data.get("itens_validados"))
    deterministic = [item for item in parser_items or step1_items if isinstance(item, dict) and _text(item.get("titulo"))]

    items: list[dict[str, Any]] = deterministic[:]

    if not deterministic:
        for item in _list(step2_data.get("atividades")):
            if isinstance(item, dict):
                items.append(
                    {
                        "titulo": item.get("titulo"),
                        "descricao": item.get("descricao"),
                        "responsavel": item.get("responsavel"),
                        "empresa_responsavel": item.get("empresa_responsavel") or item.get("responsavel"),
                        "prazo_original": item.get("prazo_original"),
                        "prazo_vigente": item.get("prazo_vigente"),
                        "status": item.get("status"),
                        "criticidade": item.get("criticidade"),
                        "secao": item.get("categoria") or "Atividades",
                        "observacoes": item.get("proximos_passos") or item.get("historico_cronologico"),
                        "fonte": item.get("fonte"),
                        "evidencia": item.get("evidencia"),
                    }
                )

        for item in _list(step2_data.get("pendencias")):
            if isinstance(item, dict):
                items.append(
                    {
                        "titulo": item.get("titulo"),
                        "descricao": item.get("descricao"),
                        "responsavel": item.get("responsavel_pendencia") or item.get("responsavel"),
                        "empresa_responsavel": item.get("tipo_responsavel"),
                        "prazo_vigente": item.get("prazo"),
                        "status": "Pendente",
                        "criticidade": item.get("criticidade"),
                        "secao": item.get("ambiente") or "Pendências",
                        "observacoes": item.get("acao_recomendada"),
                        "fonte": item.get("fonte"),
                        "evidencia": item.get("evidencia"),
                    }
                )

    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        title = _text(item.get("titulo"))
        if not title:
            continue
        key = _item_key(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _active_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if _is_active(item)]


def _informative_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if _is_informative(item)]


def _concluded_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if _is_concluded(item)]


def _current_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if "ata atual" in _norm_key(item.get("secao"))]


def _latest_note(item: dict[str, Any]) -> str:
    obs = _text(item.get("observacoes"))
    obs_date = _text(item.get("observacao_data"))
    if obs and obs_date:
        return f"{obs_date} - {obs}"
    return obs


def _history_entries(item: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for entry in _list(item.get("historico_observacoes")):
        if not isinstance(entry, dict):
            continue
        text = _text(entry.get("texto"))
        label = _text(entry.get("data"))
        if text:
            entries.append({"date": label, "text": text})
    return entries


def _history_text(item: dict[str, Any]) -> str:
    entries = _history_entries(item)
    if not entries:
        return ""
    return " | ".join(f"{e['date']} - {e['text']}" if e.get('date') else e['text'] for e in entries)


def _item_body(item: dict[str, Any]) -> str:
    desc = _text(item.get("descricao"), "Registro da ata para acompanhamento.")
    obs = _latest_note(item)
    if obs and _norm_key(obs) not in _norm_key(desc):
        return f"{desc} Última observação: {obs}"
    return desc


def _action_text(item: dict[str, Any]) -> str:
    obs = _latest_note(item)
    if _is_informative(item):
        return "Registro informativo da ata; não classificado como pendência."
    if _is_concluded(item):
        return "Item concluído ou baixado em ata."
    if obs:
        return obs
    prazo = _to_iso_or_text(item.get("prazo_vigente") or item.get("prazo"))
    responsible = _text(item.get("responsavel") or item.get("empresa_responsavel"), "Indefinido")
    if prazo and responsible != "Indefinido":
        return f"Acompanhar atendimento por {responsible} até {prazo}."
    if prazo:
        return f"Acompanhar atendimento até {prazo}."
    if responsible != "Indefinido":
        return f"Acompanhar retorno de {responsible}."
    return "Complementar responsável e prazo na próxima atualização da ata."


def _sla_tags(item: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    incidencia = item.get("incidencia_detectada")
    reprogramacoes = item.get("reprogramacoes_detectadas")
    if incidencia:
        tags.append(f"Incidência: {incidencia}")
    if reprogramacoes:
        tags.append(f"Reprogramações: {reprogramacoes}")
    indicador = _text(item.get("sla_indicador"))
    if indicador:
        tags.append(indicador)
    return tags


def _critical_from_items(items: list[dict[str, Any]], data_ref: date | None) -> list[dict[str, Any]]:
    active = _active_items(items)
    scored: list[tuple[int, dict[str, Any], str]] = []
    for item in active:
        level = _normalize_level(item.get("criticidade"), item, data_ref)
        score = {"critico": 4, "alto": 3, "moderado": 2, "baixo": 1}.get(level, 1)
        score += min(int(item.get("incidencia_detectada") or 1), 4) - 1
        prazo = _date_obj(item.get("prazo_vigente") or item.get("prazo"))
        if data_ref and prazo and prazo < data_ref:
            score += 3
        if "ata atual" in _norm_key(item.get("secao")):
            score += 1
        scored.append((score, item, level))

    scored.sort(key=lambda row: row[0], reverse=True)
    selected = [(score, item, level) for score, item, level in scored if level in {"critico", "alto"}]
    if not selected:
        selected = scored[:3]

    result: list[dict[str, Any]] = []
    for index, (_, item, level) in enumerate(selected[:6], start=1):
        prazo = _to_iso_or_text(item.get("prazo_vigente") or item.get("prazo")) or "Não informado"
        responsible = _text(item.get("responsavel") or item.get("empresa_responsavel"), "Indefinido")
        tags = [_status_text(item), f"Prazo: {prazo}", f"Responsável: {responsible}", *_sla_tags(item)]
        if item.get("numero_ata_origem"):
            tags.append(f"Ata {item.get('numero_ata_origem')}")
        result.append(
            {
                "id": _text(item.get("id_item"), _safe_id(index)),
                "title": _text(item.get("titulo")),
                "level": level,
                "body": _item_body(item),
                "tags": tags,
                "action": _action_text(item),
            }
        )
    return result


def _pendencias_from_items(items: list[dict[str, Any]], data_ref: date | None) -> list[dict[str, Any]]:
    active = _active_items(items)
    result = []
    for index, item in enumerate(active[:30], start=1):
        level = _normalize_level(item.get("criticidade"), item, data_ref)
        area = _section_label(item)
        prazo = _to_iso_or_text(item.get("prazo_vigente") or item.get("prazo"))
        extra = f" Prazo vigente: {prazo}." if prazo else ""
        result.append(
            {
                "id": _safe_id(index),
                "title": _text(item.get("titulo")),
                "desc": f"{_item_body(item)}{extra}",
                "area": area,
                "level": _level_label(level),
                "history": _history_entries(item),
            }
        )
    return result


def _plano_from_items(items: list[dict[str, Any]], data_ref: date | None) -> list[dict[str, Any]]:
    active = _active_items(items)
    ranked: list[tuple[int, dict[str, Any], str]] = []
    for item in active:
        level = _normalize_level(item.get("criticidade"), item, data_ref)
        score = {"critico": 4, "alto": 3, "moderado": 2, "baixo": 1}.get(level, 1)
        score += min(int(item.get("incidencia_detectada") or 1), 3) - 1
        ranked.append((score, item, level))
    ranked.sort(key=lambda row: row[0], reverse=True)

    result = []
    for index, (_, item, level) in enumerate(ranked[:8], start=1):
        prazo = _to_iso_or_text(item.get("prazo_vigente") or item.get("prazo")) or "Não informado"
        responsible = _text(item.get("responsavel") or item.get("empresa_responsavel"), "Indefinido")
        result.append(
            {
                "id": _safe_id(index),
                "title": _text(item.get("titulo")),
                "body": _action_text(item),
                "meta": f"{responsible} · {prazo}",
                "level": _priority_label(level),
            }
        )
    return result


def _schedule_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active = _active_items(items)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in active[:40]:
        group = _section_label(item)
        grouped.setdefault(group, []).append(item)

    schedule = []
    for group, group_items in grouped.items():
        rows = []
        for item in group_items:
            status, label = _status_to_template(item.get("status"))
            rows.append(
                {
                    "item": _text(item.get("titulo")),
                    "resp": _text(item.get("responsavel") or item.get("empresa_responsavel"), "Indefinido"),
                    "start": _to_iso_or_text(item.get("data_item")) or "Não informado",
                    "end": _to_iso_or_text(item.get("prazo_vigente") or item.get("prazo")) or "Não informado",
                    "progress": item.get("avanco_percentual"),
                    "status": status,
                    "statusLabel": label,
                    "history": _history_entries(item),
                }
            )
        schedule.append({"group": group, "rows": rows})
    return schedule


def _phases_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return []
    active = _active_items(items)
    informative = _informative_items(items)
    concluded = _concluded_items(items)
    current = _current_items(items)
    total = max(len(items), 1)
    closed_pct = round((len(concluded) + len(informative)) / total * 100)
    return [
        {"name": "Itens ativos", "progress": None, "note": f"{len(active)} itens pendentes/em andamento detectados na ata."},
        {"name": "Informativos formais", "progress": None, "note": f"{len(informative)} registros informativos separados das pendências."},
        {"name": "Itens concluídos", "progress": closed_pct, "note": f"{len(concluded)} itens concluídos ou baixados em ata."},
        {"name": "Itens da ata atual", "progress": None, "note": f"{len(current)} itens registrados na ata atual."},
    ]


def _ata_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current = _current_items(items)
    informatives = [item for item in _informative_items(items) if item not in current]
    source = current + informatives
    if not source:
        source = items[:8]
    result = []
    for index, item in enumerate(source[:24], start=1):
        status = _status_text(item)
        decision = _action_text(item)
        result.append(
            {
                "id": index,
                "tag": status,
                "title": _text(item.get("titulo")),
                "body": _item_body(item),
                "decision": decision,
                "history": _history_entries(item),
            }
        )
    return result


def _concluidos_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for index, item in enumerate(_concluded_items(items)[:20], start=1):
        result.append(
            {
                "id": _safe_id(index),
                "title": _text(item.get("titulo")),
                "desc": _item_body(item),
                "responsible": _text(item.get("responsavel") or item.get("empresa_responsavel"), "Indefinido"),
                "date": _to_iso_or_text(item.get("prazo_vigente") or item.get("data_item")) or "Não informado",
                "history": _history_entries(item),
            }
        )
    return result


def _deliberacoes_from_items(items: list[dict[str, Any]], data_ref: date | None) -> list[dict[str, Any]]:
    # Deliberação não é lista de todas as pendências antigas: prioriza itens da ata atual e informativos formais.
    selected: list[dict[str, Any]] = []
    for item in _current_items(items):
        selected.append(item)
    for item in _informative_items(items):
        key = _item_key(item)
        if key not in {_item_key(existing) for existing in selected}:
            selected.append(item)

    result = []
    for item in selected[:18]:
        level = _normalize_level(item.get("criticidade"), item, data_ref)
        mark = "✓" if _is_concluded(item) else ("○" if _is_informative(item) else ("!" if level in {"critico", "alto"} else "→"))
        prazo = _to_iso_or_text(item.get("prazo_vigente") or item.get("prazo")) or "Não informado"
        responsible = _text(item.get("responsavel") or item.get("empresa_responsavel"), "Indefinido")
        text = f"{_text(item.get('titulo'))}: {_action_text(item)}"
        if _is_informative(item):
            text = f"{_text(item.get('titulo'))}: {_item_body(item)}"
        result.append({"mark": mark, "text": text, "meta": f"{responsible} · {prazo}"})
    return result


def _ambientes_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active = _active_items(items)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in active:
        key = _text(item.get("responsavel") or item.get("empresa_responsavel"), "Indefinido")
        grouped.setdefault(key, []).append(item)
    result = []
    for responsible, group_items in list(grouped.items())[:9]:
        result.append(
            {
                "name": f"Frente inferida: {responsible}",
                "meta": f"Ambiente/frente inferido a partir da ata • {len(group_items)} item(ns) ativo(s)",
                "progress": None,
                "bullets": [_text(item.get("titulo")) for item in group_items[:6]],
            }
        )
    return result


def _ensure_meta(report: dict[str, Any], step1_data: dict[str, Any], step2_data: dict[str, Any], base_context: dict[str, Any]) -> None:
    meta = dict(report.get("meta") or {})
    doc = step1_data.get("dados_documento") or {}
    gerais = step2_data.get("dados_gerais") or {}

    meta["project"] = _text(doc.get("nome_obra") or gerais.get("obra") or base_context.get("nome_obra"), "Obra")
    meta["title"] = "Relatório Semanal de Obra"
    meta["rev"] = f"ATA {doc.get('numero_ata') or base_context.get('numero_ata') or ''}".strip()
    meta["refDate"] = _to_iso_or_text(doc.get("data_reuniao") or gerais.get("data_referencia") or base_context.get("data_reuniao_atual"))
    meta["engineer"] = _text(base_context.get("engenheiro_responsavel") or gerais.get("engenheiro_responsavel"), "Não informado")
    meta["contractDeadline"] = _to_iso_or_text(base_context.get("prazo_contratual") or gerais.get("prazo_contratual")) or "Não informado"
    meta["workingDaysLeft"] = _text((step2_data.get("metricas_resumo") or {}).get("dias_uteis_restantes"), "Não calculável")
    meta["globalProgress"] = (step2_data.get("metricas_resumo") or {}).get("avanco_global")
    meta["weeklyClosing"] = _text(gerais.get("fechamento"), "Não informado")
    meta["week"] = _text(base_context.get("semana_referencia") or gerais.get("semana_referencia"), "Semana analisada")
    report["meta"] = meta


def finalize_report_json(
    report_json: dict[str, Any],
    step2_data: dict[str, Any],
    step1_data: dict[str, Any],
    base_context: dict[str, Any],
) -> dict[str, Any]:
    """Normaliza o JSON final com a ata como fonte de verdade.

    Regras principais:
    - remove duplicidades;
    - não inventa data de início;
    - separa pendência, informativo e concluído;
    - corrige contadores do header;
    - usa incidência/reprogramação para criticidade;
    - sinaliza ambientes inferidos.
    """
    report = dict(report_json or {})
    data_ref = _date_obj(_get(step1_data, "dados_documento", "data_reuniao") or base_context.get("data_reuniao_atual"))
    items = _extract_items(step1_data, step2_data)
    active = _active_items(items)
    informative = _informative_items(items)
    concluded = _concluded_items(items)

    _ensure_meta(report, step1_data, step2_data, base_context)

    critical_points = _critical_from_items(items, data_ref)
    report["criticalPoints"] = critical_points
    report["phases"] = _phases_from_items(items)
    report["schedule"] = _schedule_from_items(items)
    report["ambientes"] = _ambientes_from_items(items)
    report["pendenciasTools"] = _pendencias_from_items(items, data_ref)
    report["planoAcao"] = _plano_from_items(items, data_ref)
    report["ata"] = _ata_from_items(items)
    report["concluidos"] = _concluidos_from_items(items)
    report["deliberacoes"] = _deliberacoes_from_items(items, data_ref)

    hero = dict(report.get("hero") or {})
    hero["headline"] = f"Relatório Atual da Obra {report['meta'].get('project', '')}".strip()
    hero["subheadline"] = (
        f"Foram identificados {len(active)} item(ns) ativo(s), {len(informative)} informativo(s) e "
        f"{len(concluded)} concluído(s)/baixado(s) na ata."
    )
    high_or_critical = [p for p in critical_points if p.get("level") in {"critico", "alto"}]
    hero["pills"] = [
        f"Itens ativos: {len(active)}",
        f"Pendências: {len(active)}",
        f"Informativos: {len(informative)}",
        f"Críticos/altos: {len(high_or_critical)}",
    ]
    report["hero"] = hero

    if critical_points:
        report["criticalAlert"] = {
            "title": "Atenção aos itens de maior recorrência",
            "body": "A criticidade considera prazo, status, incidência/SLA e reprogramações identificadas na ata.",
        }
    else:
        report["criticalAlert"] = {"title": "Sem ponto crítico consolidado", "body": "Não foram identificados bloqueios críticos nos dados recebidos."}

    quality = dict(report.get("quality") or {})
    quality["ocrLevel"] = _text(_get(step1_data, "dados_documento", "qualidade_visual"), "media")
    warnings = list(quality.get("warnings") or [])
    for alerta in _list(step1_data.get("alertas")):
        if isinstance(alerta, dict):
            message = _text(alerta.get("descricao") or alerta.get("tipo"))
            if message and message not in warnings:
                warnings.append(message)
    if items and any(a.get("meta", "").startswith("Ambiente/frente inferido") for a in report.get("ambientes", [])):
        warnings.append("A seção Status por Ambiente foi inferida por responsável/seção, pois a ata não trouxe ambientes formais nem avanço físico por ambiente.")
    quality["warnings"] = [w for w in warnings if w]
    quality.setdefault("sources", ["PDF / arquivos enviados"])
    quality.setdefault("corrections", [])
    quality.setdefault("dataGaps", [])
    report["quality"] = quality

    return report
