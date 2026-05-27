from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

MONTHS_PT = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

SECTION_TITLES = [
    "Itens Ata Anterior / Itens Pendentes",
    "Itens Ata Atual",
    "Itens Concluídos e Informativos",
]

# Cada item da ata costuma iniciar com: Item Nº Ata Data Item Responsável ...
ITEM_START_RE = re.compile(
    r"(?ms)^\s*(\d+)\s+(\d{3})\s+(\d{2}/\d{2}/\d{4})\s+(.+?)(?=^\s*\d+\s+\d{3}\s+\d{2}/\d{2}/\d{4}\s+|\Z)"
)
DATE_RE = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
OBS_RE = re.compile(r"\b(\d{2}\.\d{2}(?:\.\d{2})?)\s*-\s*(.+?)(?=(?:\n\d{2}\.\d{2}(?:\.\d{2})?\s*-)|\Z)", re.S)
STATUS_RE = re.compile(
    r"\b(Em andamento|Conclu[ií]da|Conclu[ií]do|informação|Informativo|Pendente|Bloqueante|Atrasada|Não iniciado)\b",
    re.I,
)


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.replace("\r", "")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")


def _normalize_status(value: str | None, section: str) -> str:
    text = _strip_accents((value or "").lower())
    section_norm = _strip_accents(section.lower())
    if "conclu" in text:
        return "Concluído"
    if "inform" in text:
        return "Informativo"
    if "bloque" in text:
        return "Bloqueante"
    if "atras" in text:
        return "Atrasada"
    if "nao iniciado" in text:
        return "Não iniciado"
    if "pendente" in text:
        return "Pendente"
    if "andamento" in text:
        return "Em andamento"
    if "concluidos" in section_norm or "informativos" in section_norm:
        return "Informativo"
    return "Pendente"


def _tipo_registro(section: str, status: str) -> str:
    section_norm = _strip_accents(section.lower())
    status_norm = _strip_accents(status.lower())
    if "inform" in status_norm:
        return "informativo"
    if "conclu" in status_norm:
        return "concluido"
    if "concluidos" in section_norm or "informativos" in section_norm:
        return "informativo"
    if "ata atual" in section_norm:
        return "pendencia_atual"
    return "pendencia_anterior"


def _parse_portuguese_date(text: str) -> str:
    m = re.search(r"(\d{1,2})\s+de\s+([A-Za-zçÇãÃéÉ]+)\s+de\s+(\d{4})", text, flags=re.I)
    if not m:
        return ""
    day = int(m.group(1))
    month = MONTHS_PT.get(m.group(2).lower())
    year = int(m.group(3))
    if not month:
        return ""
    return f"{day:02d}/{month:02d}/{year:04d}"


def _split_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    found: list[tuple[int, str]] = []
    for title in SECTION_TITLES:
        idx = text.find(title)
        if idx >= 0:
            found.append((idx, title))
    found.sort()

    for pos, (start, title) in enumerate(found):
        content_start = start + len(title)
        content_end = found[pos + 1][0] if pos + 1 < len(found) else len(text)
        sections[title] = text[content_start:content_end].strip()
    return sections


def _date_key(value: str) -> tuple[int, int, int]:
    try:
        d = datetime.strptime(value, "%d/%m/%Y").date()
        return (d.year, d.month, d.day)
    except ValueError:
        return (0, 0, 0)


def _valid_dates(values: list[str]) -> list[str]:
    result = []
    for value in values:
        try:
            datetime.strptime(value, "%d/%m/%Y")
        except ValueError:
            continue
        result.append(value)
    return result


def _extract_deadline_dates(rest: str, status_text: str | None) -> list[str]:
    """Extrai datas de prazo, sem usar a data do item como início.

    A data do cabeçalho do item é recebida separadamente em data_item. Aqui analisamos
    apenas o corpo do item e preferimos as datas antes do status, pois após o status
    normalmente vêm histórico/SLA/observações.
    """
    before_status = rest.split(status_text, 1)[0] if status_text else rest
    return _valid_dates(DATE_RE.findall(before_status))


def _extract_observations(block: str) -> list[dict[str, str]]:
    observations: list[dict[str, str]] = []
    for date_text, body in OBS_RE.findall(block):
        observations.append({"data": date_text.strip(), "texto": _clean_text(body)})
    return observations


def _extract_latest_observation(block: str) -> tuple[str, str]:
    observations = _extract_observations(block)
    if not observations:
        return "", ""
    latest = observations[-1]
    return latest["texto"], latest["data"]


def _line_until_control_token(line: str) -> tuple[str, bool]:
    """Preserva texto útil antes de datas/status sem truncar descrições multilinha.

    As atas em PDF frequentemente juntam descrição, prazo e status na mesma linha,
    por exemplo: ``A Cateo enviará... Art. 26/05/2026 Em andamento``.
    A função devolve o trecho descritivo e indica se a leitura da descrição deve parar.
    """
    original = _clean_text(line)
    if not original:
        return "", False
    if re.match(r"^\d{2}\.\d{2}", original):
        return "", True

    status_match = STATUS_RE.search(original)
    date_match = DATE_RE.search(original)

    cut_positions = [m.start() for m in (status_match, date_match) if m]
    if not cut_positions:
        return original, False

    first_cut = min(cut_positions)
    before = original[:first_cut].strip()

    # Se a primeira data faz parte de uma frase de prazo original, mantém a data.
    # Ex.: "... até o dia 15/04/2026. 17/04/2026".
    if date_match and first_cut == date_match.start():
        prefix = original[: date_match.start()].lower()
        if re.search(r"((até|ate)\s+(o\s+)?dia|prazo|previst[oa]|envio|entrega)$", prefix):
            end = date_match.end()
            if end < len(original) and original[end : end + 1] == ".":
                end += 1
            before = original[:end].strip()

    return before, True


def _extract_title_description_responsible(rest: str) -> tuple[str, str, str]:
    lines = [_clean_text(line) for line in rest.splitlines() if _clean_text(line)]
    title_idx = None
    for idx, line in enumerate(lines):
        if ":" in line:
            title_idx = idx
            break

    if title_idx is None:
        responsible = lines[0] if lines else "Indefinido"
        title = lines[1] if len(lines) > 1 else "Item sem título identificado"
        remaining_lines = lines[2:] if len(lines) > 2 else []
    else:
        responsible = " ".join(lines[:title_idx]).strip() or "Indefinido"
        title = lines[title_idx].split(":", 1)[0].strip()
        first_desc = lines[title_idx].split(":", 1)[1].strip()
        remaining_lines = ([first_desc] if first_desc else []) + lines[title_idx + 1 :]

    description_parts = []
    for line in remaining_lines:
        useful, should_stop = _line_until_control_token(line)
        if useful:
            description_parts.append(useful)
        elif should_stop and description_parts:
            # Em PDF extraído, o prazo pode cair sozinho na linha seguinte:
            # "... até o dia" / "15/04/2026.". Nesse caso, completa a frase
            # descritiva sem absorver toda a lista de reprogramações.
            date_match = DATE_RE.search(line)
            if date_match and re.search(r"((até|ate)\s+(o\s+)?dia|prazo|previst[oa]|envio|entrega)$", description_parts[-1].lower()):
                end = date_match.end()
                suffix = "." if end < len(line) and line[end : end + 1] == "." else ""
                description_parts[-1] = f"{description_parts[-1]} {date_match.group(0)}{suffix}"
        if should_stop:
            break

    description = _clean_text("\n".join(description_parts))
    return responsible, title, description


def _disambiguate_title(title: str, description: str) -> str:
    title_norm = _strip_accents(title.lower())
    desc_norm = _strip_accents(description.lower())
    if title_norm.strip() == "mapa mao de obra civil":
        if "instalacoes eletricas" in desc_norm or "hidraulicas" in desc_norm:
            return "Mapa mão de obra civil - Instalações elétricas e hidráulicas"
        return "Mapa de mão de obra civil"
    return title


def _calc_incidence(block: str, deadline_dates: list[str]) -> tuple[int, int, str]:
    observations = _extract_observations(block)
    obs_count = len(observations)
    reprogramacoes = max(0, len(deadline_dates) - 1)
    incidencia = max(1, obs_count)
    if incidencia >= 4 or reprogramacoes >= 3:
        indicador = "reincidência alta / várias reprogramações"
    elif incidencia >= 2 or reprogramacoes >= 1:
        indicador = "item recorrente / houve reprogramação"
    else:
        indicador = "registro pontual"
    return incidencia, reprogramacoes, indicador


def _parse_items(section: str, section_text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for match in ITEM_START_RE.finditer(section_text):
        numero_item, numero_ata, data_item, rest = match.groups()
        block = match.group(0)
        status_match = STATUS_RE.search(block)
        status_raw = status_match.group(1) if status_match else ""
        status = _normalize_status(status_raw, section)
        responsible, title, description = _extract_title_description_responsible(rest)
        title = _disambiguate_title(title, description)
        deadline_dates = _extract_deadline_dates(rest, status_raw)
        all_dates = _valid_dates(DATE_RE.findall(block))
        observacoes_historico = _extract_observations(block)
        latest_observation, latest_observation_date = _extract_latest_observation(block)
        incidencia, reprogramacoes, sla_indicador = _calc_incidence(block, deadline_dates)

        prazo_original = deadline_dates[0] if deadline_dates else ""
        prazo_anterior = deadline_dates[-2] if len(deadline_dates) >= 2 else ""
        prazo_vigente = deadline_dates[-1] if deadline_dates else ""
        if prazo_original and prazo_vigente and _date_key(prazo_vigente) < _date_key(prazo_original):
            prazo_vigente = max(deadline_dates, key=_date_key)

        items.append(
            {
                "id_item": f"ATA-{numero_ata}-ITEM-{numero_item}",
                "numero_item": numero_item,
                "numero_ata_origem": numero_ata,
                "data_item": data_item,
                "secao": section,
                "tipo_registro": _tipo_registro(section, status),
                "titulo": title,
                "descricao": description,
                "responsavel": responsible,
                "empresa_responsavel": responsible,
                "prazo_original": prazo_original,
                "prazo_anterior": prazo_anterior,
                "prazo_vigente": prazo_vigente,
                "status": status,
                "observacoes": latest_observation,
                "observacao_data": latest_observation_date,
                "historico_observacoes": observacoes_historico,
                "todas_datas_lidas": all_dates,
                "incidencia_detectada": incidencia,
                "reprogramacoes_detectadas": reprogramacoes,
                "sla_indicador": sla_indicador,
                "ambiente_inferido": False,
                "fonte": "PDF",
                "pagina": "",
                "confianca": "media",
                "evidencia": _clean_text(block[:1200]),
            }
        )
    return items


def parse_ata_text(text: str) -> dict[str, Any]:
    """Extrai uma base determinística de atas TOOLS em tabela PDF.

    A IA continua sendo a camada redacional, mas este parser é a fonte de verdade
    para itens de ata, impedindo que pendências, informativos e concluídos sejam
    perdidos ou duplicados no relatório final.
    """
    text = _clean_text(text)
    if not text:
        return {"itens_validados": [], "alertas": []}

    first_number = re.search(r"^\s*(\d{3})\s*$", text, flags=re.M)
    numero_ata = first_number.group(1) if first_number else ""
    data_reuniao = _parse_portuguese_date(text)

    obra_match = re.search(r"Cliente\s*/\s*Obra:\s*(.+)", text, flags=re.I)
    obra = _clean_text(obra_match.group(1)) if obra_match else ""

    sections = _split_sections(text)
    items: list[dict[str, Any]] = []
    for section, section_text in sections.items():
        items.extend(_parse_items(section, section_text))

    alertas = []
    for item in items:
        for data_lida in item.get("todas_datas_lidas", []):
            if data_lida.endswith("2925"):
                alertas.append(
                    {
                        "tipo": "data_suspeita",
                        "descricao": f"Data possivelmente com erro de OCR: {data_lida}",
                        "trecho_ou_item_relacionado": item.get("titulo", ""),
                        "acao_recomendada": "Validar manualmente a data no PDF.",
                    }
                )

    return {
        "dados_documento_extraidos": {
            "numero_ata": numero_ata,
            "data_reuniao": data_reuniao,
            "nome_obra": obra,
            "quantidade_itens_detectados": len(items),
        },
        "itens_validados": items,
        "alertas": alertas,
    }


def _item_key(item: dict[str, Any]) -> tuple[str, str, str]:
    title = _strip_accents(str(item.get("titulo", "")).lower())
    title = re.sub(r"[^a-z0-9]+", " ", title).strip()
    return (str(item.get("numero_ata_origem", "")), str(item.get("numero_item", "")), title)


def merge_parsed_ata_with_gpt(step1_data: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    if not parsed or not parsed.get("itens_validados"):
        return step1_data

    merged = dict(step1_data or {})
    dados_documento = dict(merged.get("dados_documento") or {})
    parsed_doc = parsed.get("dados_documento_extraidos") or {}
    for key in ("numero_ata", "data_reuniao", "nome_obra"):
        if parsed_doc.get(key) and not dados_documento.get(key):
            dados_documento[key] = parsed_doc[key]
    if parsed_doc.get("quantidade_itens_detectados"):
        dados_documento["quantidade_itens_detectados_parser"] = parsed_doc["quantidade_itens_detectados"]
    merged["dados_documento"] = dados_documento

    existing = [item for item in (merged.get("itens_validados") or []) if isinstance(item, dict)]
    existing_keys = {_item_key(item) for item in existing}
    for item in parsed.get("itens_validados") or []:
        if not isinstance(item, dict):
            continue
        key = _item_key(item)
        if key not in existing_keys:
            existing.append(item)
            existing_keys.add(key)
    merged["itens_validados"] = existing

    alertas = list(merged.get("alertas") or [])
    alertas.extend(parsed.get("alertas") or [])
    merged["alertas"] = alertas
    merged["parser_ata_tools"] = parsed
    return merged
