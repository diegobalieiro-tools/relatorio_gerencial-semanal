from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import re
from typing import Any

from app.models.obra import Obra
from app.models.relatorio import RelatorioSemanal
from app.services.normalization_service import normalizar_criticidade, normalizar_status, safe_date, safe_text


INFORMACAO_NAO_INFORMADA = "Não informado"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any, default: str = "") -> str:
    txt = safe_text(value, default)
    return txt if txt else default


def _date_br(value: Any, default: str = INFORMACAO_NAO_INFORMADA) -> str:
    parsed = safe_date(value)
    if parsed:
        return parsed.strftime("%d/%m/%Y")
    txt = _text(value)
    return txt if txt else default


def _number(value: Any) -> int | float | None:
    if value in (None, "", INFORMACAO_NAO_INFORMADA):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        txt = str(value).strip().replace("%", "").replace(",", ".")
        return float(txt)
    except (TypeError, ValueError):
        return None


def _progress(value: Any) -> int | None:
    num = _number(value)
    if num is None:
        return None
    return int(max(0, min(100, round(num))))




_DATE_RE = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
_STATUS_RE = re.compile(r"\b(Em\s+andamento|Conclu[ií]da|Conclu[ií]do|Informação|Informacao|Pendente|Atrasada|Bloqueante)\b", re.IGNORECASE)
_ROW_START_RE = re.compile(r"(?m)^\s*(\d{1,3})\s+(\d{3})\s+(\d{2}/\d{2}/\d{4})\s+(.*)$")
_SECTION_ALIASES = {
    "pendentes": "Itens Ata Anterior / Pendentes",
    "atuais": "Itens Ata Atual",
    "concluidos": "Itens Concluídos e Informativos",
}


def _all_dates(text: str) -> list[str]:
    return _DATE_RE.findall(text or "")


def _looks_like_responsavel_line(line: str) -> bool:
    txt = (line or "").strip()
    if not txt:
        return False
    # Linhas de responsável geralmente vêm em caixa alta, podendo conter barras e espaços.
    letters = re.sub(r"[^A-Za-zÀ-ÿ]", "", txt)
    if not letters:
        return False
    upper_letters = sum(1 for ch in letters if ch.upper() == ch)
    return upper_letters / max(len(letters), 1) > 0.70 and len(txt) <= 70


def _status_from_text(text: str, default: str = "Em andamento") -> str:
    m = _STATUS_RE.search(text or "")
    if not m:
        return default
    raw = m.group(1).lower()
    if "inform" in raw:
        return "Informativo"
    if "conclu" in raw:
        return "Concluído"
    if "atras" in raw:
        return "Atrasada"
    if "bloque" in raw:
        return "Bloqueante"
    if "pendent" in raw:
        return "Pendente"
    return "Em andamento"


def _extract_incidence(text: str) -> int | None:
    m = re.search(r"\b(?:Em\s+andamento|Pendente|Atrasada|Bloqueante)\s+(\d{1,2})\b", text or "", re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _strip_status_tail(text: str) -> str:
    # Remove bloco de datas/status/incidência do final da descrição, preservando observações depois do status.
    if not text:
        return ""
    m = _STATUS_RE.search(text)
    before = text[:m.start()] if m else text
    # Se houver bloco final de datas, usa o texto antes desse bloco. Mantém frases que citam data no meio.
    date_matches = list(_DATE_RE.finditer(before))
    if date_matches:
        first_date = date_matches[0]
        candidate = before[: first_date.start()].strip()
        if len(candidate) >= 25:
            return candidate
    return before.strip()


def _observacao_from_text(text: str) -> str:
    if not text:
        return ""
    m = _STATUS_RE.search(text)
    if not m:
        return ""
    obs = text[m.end():].strip()
    obs = re.sub(r"^\s*\d{1,2}\s+", "", obs)
    return obs.strip()


def _split_ocr_sections(text: str) -> dict[str, str]:
    """Separa o texto OCR por blocos da ata.

    A ata escaneada usa títulos de seção como:
    - Itens Ata Anterior / Itens Pendentes
    - Itens Ata Atual
    - Itens Concluídos e Informativos
    """
    if not text:
        return {}
    markers: list[tuple[int, str]] = []
    patterns = [
        ("pendentes", r"Itens\s+Ata\s+Anterior\s*/\s*(?:Itens\s+)?Pendentes"),
        ("atuais", r"Itens\s+Ata\s+Atual"),
        ("concluidos", r"Itens\s+Conclu[ií]dos\s+e\s+Informativos"),
    ]
    for key, pat in patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            markers.append((m.start(), key))
            break
    markers.sort()
    out: dict[str, str] = {}
    for idx, (start, key) in enumerate(markers):
        end = markers[idx + 1][0] if idx + 1 < len(markers) else len(text)
        out[key] = text[start:end]
    return out


def _parse_ocr_section_rows(section_text: str, section_key: str, ata_atual: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not section_text:
        return rows
    matches = list(_ROW_START_RE.finditer(section_text))
    for i, match in enumerate(matches):
        row_start = match.start()
        row_end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)
        block = section_text[row_start:row_end].strip()
        if not block:
            continue

        numero_item = match.group(1).strip()
        numero_ata = match.group(2).strip()
        data_item = match.group(3).strip()
        after_header_first_line = match.group(4).strip()

        # Reconstrói linhas a partir da primeira linha já capturada após a data.
        rest = block[match.end() - row_start :].strip()
        lines = [after_header_first_line] + [ln.strip() for ln in rest.splitlines() if ln.strip()]
        # Remove ruídos de rodapé/cabeçalho frequentemente capturados após o último item.
        clean_lines: list[str] = []
        for ln in lines:
            if re.search(r"^(Disciplina|Construtora\s+\S+@|ATA DE REUNIÃO|Cliente / Obra|Gerenciamento\s+\S+@)", ln, re.IGNORECASE):
                break
            clean_lines.append(ln)
        lines = clean_lines
        if not lines:
            continue

        title_idx = None
        for idx, ln in enumerate(lines):
            if ln.endswith(":") and len(ln) > 2:
                title_idx = idx
                break
        if title_idx is None:
            # fallback: primeira linha que não parece responsável
            for idx, ln in enumerate(lines):
                if not _looks_like_responsavel_line(ln):
                    title_idx = idx
                    break
        if title_idx is None:
            continue

        resp_lines = [ln for ln in lines[:title_idx] if ln]
        responsavel = " ".join(resp_lines).strip(" -") or "Indefinido"
        titulo = lines[title_idx].rstrip(":").strip()
        body = "\n".join(lines[title_idx + 1:]).strip()
        if _is_placeholder(titulo):
            continue

        status = _status_from_text(body, default="Informativo" if section_key == "concluidos" else "Em andamento")
        if section_key == "concluidos" and status == "Em andamento":
            status = "Concluído" if re.search(r"\bConclu[ií]d[ao]\b", body, re.IGNORECASE) else _status_from_text(body, "Informativo")

        status_match = _STATUS_RE.search(body)
        pre_status = body[: status_match.start()] if status_match else body
        dates_before_status = _all_dates(pre_status)
        all_dates = _all_dates(body)
        prazo_original = dates_before_status[0] if dates_before_status else ""
        prazo_vigente = dates_before_status[-1] if dates_before_status else ""
        if status == "Informativo":
            prazo_vigente = ""
        descricao = _strip_status_tail(body) or "Registro da ata para acompanhamento."
        observacao = _observacao_from_text(body)
        incidencia = _extract_incidence(body)
        reprogramacoes = max(0, len(set(dates_before_status)) - 1)
        recorrente = section_key == "pendentes" or (incidencia or 0) > 1 or (ata_atual and numero_ata != ata_atual)

        if status == "Informativo" or status == "Concluído":
            criticidade = "Baixa"
        elif (incidencia or 0) >= 2 or reprogramacoes >= 2:
            criticidade = "Alta"
        elif section_key == "pendentes" or reprogramacoes >= 1:
            criticidade = "Média"
        else:
            criticidade = "Média"

        rows.append(
            {
                "id": f"ATA-{numero_ata}-ITEM-{numero_item}",
                "id_item": f"ATA-{numero_ata}-ITEM-{numero_item}",
                "numero_item": numero_item,
                "numero_ata_origem": numero_ata,
                "data_abertura": data_item,
                "titulo": titulo,
                "descricao": descricao,
                "observacoes": observacao,
                "evidencia": block[:1200],
                "categoria": _SECTION_ALIASES.get(section_key, "Itens da Ata"),
                "secao": _SECTION_ALIASES.get(section_key, "Itens da Ata"),
                "status": status,
                "criticidade": criticidade,
                "responsavel": responsavel,
                "empresa_responsavel": responsavel,
                "prazo_original": prazo_original,
                "prazo_vigente": prazo_vigente,
                "fonte": "PDF/OCR",
                "item_recorrente": bool(recorrente),
                "houve_reprogramacao": reprogramacoes > 0,
                "incidencia": incidencia,
                "quantidade_reprogramacoes": reprogramacoes,
                "datas_lidas": all_dates,
                "ata_atual": section_key == "atuais",
                "historico_secao": section_key,
            }
        )
    return rows


def _collect_atividades_from_texto_ocr(extracao: dict[str, Any] | None, ata_atual: str | None = None) -> list[dict[str, Any]]:
    if not isinstance(extracao, dict):
        return []
    texts = []
    # Usa tanto a saída validada do GPT 1 quanto o texto bruto extraído dos arquivos.
    # O texto bruto é essencial para não perder linhas da tabela quando o GPT 1 resume demais.
    for key in [
        "texto_validado",
        "texto_extraido",
        "raw_text",
        "conteudo_textual",
        "arquivos_contexto_extraido",
        "files_context_text",
        "texto_bruto_arquivos",
    ]:
        txt = _text(extracao.get(key))
        if txt:
            texts.append(txt)
    # Algumas leituras guardam tabelas reconstruídas como linhas dentro de tabelas_identificadas.
    for tabela in _as_list(extracao.get("tabelas_identificadas")):
        if not isinstance(tabela, dict):
            continue
        linhas = tabela.get("linhas")
        if isinstance(linhas, list) and linhas:
            texts.append("\n".join(str(l) for l in linhas))
    combined = "\n".join(texts)
    if not combined:
        return []
    sections = _split_ocr_sections(combined)
    parsed: list[dict[str, Any]] = []
    for key in ["pendentes", "atuais", "concluidos"]:
        parsed.extend(_parse_ocr_section_rows(sections.get(key, ""), key, ata_atual=ata_atual))
    return _dedupe_items(parsed)


def _nivel_template(value: Any) -> str:
    nivel = normalizar_criticidade(value) or "moderado"
    if nivel == "baixo":
        return "baixo"
    return nivel


def _level_label(value: Any) -> str:
    nivel = _nivel_template(value)
    return {
        "critico": "Crítica",
        "alto": "Alta",
        "moderado": "Média",
        "baixo": "Baixa",
    }.get(nivel, "Média")


def _status_template(value: Any) -> str:
    status = normalizar_status(value) or "andamento"
    return {
        "concluido": "concluido",
        "andamento": "andamento",
        "pendente": "bloqueado",
        "bloqueante": "bloqueado",
        "nao_iniciado": "nao-iniciado",
        "informativo": "planejado",
    }.get(status, status)


def _status_label(value: Any) -> str:
    status = normalizar_status(value) or "andamento"
    return {
        "concluido": "Concluído",
        "andamento": "Em andamento",
        "pendente": "Pendente",
        "bloqueante": "Bloqueante",
        "nao_iniciado": "Não iniciado",
        "informativo": "Informativo",
    }.get(status, _text(value, "Em andamento"))


def _mark_for_status(status: Any, criticidade: Any = None) -> str:
    nivel = _nivel_template(criticidade)
    norm = normalizar_status(status)
    if nivel in {"critico", "alto"} or norm == "bloqueante":
        return "!"
    if norm == "concluido":
        return "✓"
    if norm == "andamento":
        return "→"
    return "○"


def _get_dados_gerais(dados: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(dados.get("dados_gerais"))


def _atividade_titulo(item: dict[str, Any]) -> str:
    return _text(item.get("titulo") or item.get("title") or item.get("frente") or item.get("ambiente_ou_pacote"), "Item sem título")


def _atividade_descricao(item: dict[str, Any]) -> str:
    partes = [
        _text(item.get("descricao") or item.get("description")),
        _text(item.get("observacoes") or item.get("observacao")),
        _text(item.get("historico_cronologico")),
        _text(item.get("evidencia")),
    ]
    texto = " ".join(p for p in partes if p).strip()
    return texto or "Registro da ata para acompanhamento."


def _atividade_acao(item: dict[str, Any]) -> str:
    return (
        _text(item.get("proximos_passos"))
        or _text(item.get("acao_recomendada"))
        or _text(item.get("observacoes"))
        or _text(item.get("observacao"))
        or "Acompanhar responsável e prazo vigente."
    )


def _atividade_prazo(item: dict[str, Any]) -> str:
    return _date_br(item.get("prazo_vigente") or item.get("prazo") or item.get("termino") or item.get("prazo_limite"))


def _atividade_responsavel(item: dict[str, Any]) -> str:
    return _text(
        item.get("responsavel")
        or item.get("responsavel_pendencia")
        or item.get("empresa_responsavel")
        or item.get("responsible"),
        "Indefinido",
    )


def _atividade_categoria(item: dict[str, Any]) -> str:
    return _text(item.get("categoria") or item.get("secao") or item.get("grupo") or item.get("ambiente"), "Itens da Semana")


_PLACEHOLDER_TITLES = {
    "",
    "item sem título",
    "item sem titulo",
    "item do cronograma",
    "ponto crítico sem título",
    "ponto critico sem titulo",
    "ação semanal",
    "acao semanal",
}


def _norm_key(value: Any) -> str:
    txt = _text(value).strip().lower()
    for old, new in [("á", "a"), ("à", "a"), ("ã", "a"), ("â", "a"), ("é", "e"), ("ê", "e"), ("í", "i"), ("ó", "o"), ("ô", "o"), ("õ", "o"), ("ú", "u"), ("ç", "c")]:
        txt = txt.replace(old, new)
    return " ".join(txt.split())


def _is_placeholder(value: Any) -> bool:
    txt = _norm_key(value)
    if txt in _PLACEHOLDER_TITLES:
        return True
    if txt.startswith("item do cronograma") or txt.startswith("item sem titulo"):
        return True
    return False


def _item_quality(item: dict[str, Any]) -> int:
    """Pontua a riqueza do item para escolher a versão mais informativa em merges."""
    if not isinstance(item, dict):
        return 0
    score = 0
    for key in ["titulo", "title", "descricao", "description", "observacoes", "observacao", "historico_cronologico", "evidencia", "prazo_vigente", "prazo", "termino", "responsavel", "empresa_responsavel", "criticidade", "status"]:
        if _text(item.get(key)):
            score += 1
    if not _is_placeholder(_atividade_titulo(item)):
        score += 8
    if _text(item.get("descricao") or item.get("description")):
        score += 4
    return score


def _merge_item(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Mescla dois itens preservando o que já for bom e preenchendo lacunas."""
    if _item_quality(incoming) > _item_quality(base):
        primary, secondary = dict(incoming), base
    else:
        primary, secondary = dict(base), incoming
    for key, value in secondary.items():
        if primary.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
            primary[key] = value
    return primary


def _atividade_key(item: dict[str, Any]) -> str:
    titulo = _norm_key(_atividade_titulo(item))
    prazo = _norm_key(_atividade_prazo(item))
    secao = _norm_key(_atividade_categoria(item))
    if _is_placeholder(titulo):
        return f"{titulo}|{secao}|{prazo}|{_norm_key(_atividade_descricao(item))[:80]}"
    return f"{titulo}|{secao}|{prazo}"


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = _atividade_key(item)
        if key not in merged:
            merged[key] = item
            order.append(key)
        else:
            merged[key] = _merge_item(merged[key], item)
    return [merged[k] for k in order]


def _adapt_item_validado(item: dict[str, Any]) -> dict[str, Any]:
    """Converte item do GPT1 (`itens_validados`) para o formato de atividade do GPT2."""
    titulo = _text(item.get("titulo") or item.get("title"), "Item sem título")
    descricao = _text(item.get("descricao") or item.get("description"))
    observacoes = _text(item.get("observacoes") or item.get("observacao"))
    evidencia = _text(item.get("evidencia"))
    status = _text(item.get("status"), "Em andamento")
    secao = _text(item.get("secao"), "Itens da Ata")
    criticidade = _text(item.get("criticidade"))
    norm_status = normalizar_status(status)
    if not criticidade:
        if norm_status in {"bloqueante", "pendente"}:
            criticidade = "Alta"
        elif norm_status == "concluido" or norm_status == "informativo":
            criticidade = "Baixa"
        else:
            criticidade = "Média"
    return {
        "id": _text(item.get("id") or item.get("id_item") or item.get("numero_item")),
        "id_item": _text(item.get("id_item") or item.get("id") or item.get("numero_item")),
        "titulo": titulo,
        "descricao": descricao or "Registro da ata para acompanhamento.",
        "observacoes": observacoes,
        "evidencia": evidencia,
        "categoria": secao,
        "secao": secao,
        "status": status,
        "criticidade": criticidade,
        "responsavel": _text(item.get("responsavel") or item.get("empresa_responsavel"), "Indefinido"),
        "empresa_responsavel": _text(item.get("empresa_responsavel") or item.get("responsavel"), "Indefinido"),
        "prazo_original": _text(item.get("prazo_original")),
        "prazo_vigente": _text(item.get("prazo_vigente") or item.get("prazo") or item.get("prazo_limite")),
        "fonte": _text(item.get("fonte"), "PDF"),
        "data_abertura": _text(item.get("data_abertura")),
        "data_ultima_atualizacao": _text(item.get("data_ultima_atualizacao")),
        "item_recorrente": bool(item.get("item_recorrente", False)),
        "houve_reprogramacao": bool(item.get("houve_reprogramacao", False)),
    }


def _collect_atividades_from_extracao(extracao: dict[str, Any] | None, ata_atual: str | None = None) -> list[dict[str, Any]]:
    if not isinstance(extracao, dict):
        return []
    atividades: list[dict[str, Any]] = []
    for item in _as_list(extracao.get("itens_validados")):
        if isinstance(item, dict):
            atividades.append(_adapt_item_validado(item))
    # Alguns OCRs estruturam pendências/decisões fora de itens_validados.
    for item in _as_list(extracao.get("pendencias_validadas")):
        if isinstance(item, dict):
            atividades.append(_adapt_item_validado({**item, "secao": "Pendências", "status": item.get("status") or "Pendente"}))
    for item in _as_list(extracao.get("decisoes_validadas")):
        if isinstance(item, dict):
            atividades.append(_adapt_item_validado({**item, "secao": "Deliberações", "status": item.get("status") or "Informativo"}))

    # OCR bruto: garante que itens pendentes de atas anteriores não sejam perdidos
    # quando o GPT resumir apenas a seção "Itens Ata Atual".
    atividades_ocr = _collect_atividades_from_texto_ocr(extracao, ata_atual=ata_atual)
    if atividades_ocr:
        atividades.extend(atividades_ocr)

    return _dedupe_items(atividades)


def _looks_weak_items(items: list[dict[str, Any]], min_good: int = 2) -> bool:
    if not items:
        return True
    good = 0
    for item in items:
        if not _is_placeholder(_atividade_titulo(item)) and _text(_atividade_descricao(item)) not in {"Registro da ata para acompanhamento."}:
            good += 1
    return good < min_good


def _collect_atividades(dados: dict[str, Any], extracao: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    atividades: list[dict[str, Any]] = []
    ata_atual = _text(_get_dados_gerais(dados).get("numero_ata"))

    # Fonte principal: GPT2 estruturado.
    for item in _as_list(dados.get("atividades")):
        if isinstance(item, dict):
            atividades.append(item)

    persist = _as_dict(dados.get("dados_para_persistencia"))
    for item in _as_list(persist.get("itens_acompanhamento")):
        if isinstance(item, dict):
            atividades.append(item)

    # Complementos do GPT2 quando a lista principal veio pobre.
    for item in _as_list(dados.get("cronograma_executivo")):
        if isinstance(item, dict):
            titulo = _text(item.get("titulo") or item.get("frente") or item.get("ambiente_ou_pacote"))
            if titulo and not _is_placeholder(titulo):
                atividades.append(
                    {
                        "titulo": titulo,
                        "descricao": _text(item.get("observacao") or item.get("descricao"), "Registro de cronograma."),
                        "categoria": _text(item.get("grupo"), "Cronograma Executivo"),
                        "status": _text(item.get("status"), "Em andamento"),
                        "criticidade": _text(item.get("criticidade"), "Média"),
                        "responsavel": _text(item.get("responsavel"), "Indefinido"),
                        "prazo_vigente": _text(item.get("termino") or item.get("prazo_reprogramado")),
                        "avanco_percentual": item.get("avanco_percentual"),
                    }
                )

    for item in _as_list(dados.get("pendencias")):
        if isinstance(item, dict):
            atividades.append(item)

    # Fonte de segurança: GPT1/OCR validado. Essa etapa costuma preservar melhor os itens da ata.
    atividades_gpt1 = _collect_atividades_from_extracao(extracao, ata_atual=ata_atual)
    if atividades_gpt1:
        # Sempre adiciona o GPT1 para não perder item; o dedupe escolhe a versão mais rica.
        atividades.extend(atividades_gpt1)

    atividades = _dedupe_items(atividades)

    # Se o GPT2 retornou itens genéricos, descarte placeholders quando houver itens reais do GPT1.
    if atividades_gpt1 and _looks_weak_items([a for a in atividades if a not in atividades_gpt1], min_good=2):
        atividades = _dedupe_items(atividades_gpt1 + [a for a in atividades if not _is_placeholder(_atividade_titulo(a))])

    return atividades


def _collect_pendencias(dados: dict[str, Any], atividades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pendencias: list[dict[str, Any]] = []
    for item in _as_list(dados.get("pendencias")):
        if isinstance(item, dict):
            pendencias.append(item)

    ativos = [item for item in atividades if normalizar_status(item.get("status")) not in {"concluido", "informativo"}]

    # Se GPT2 trouxe poucas pendências ou uma pendência genérica, completa com os itens ativos da ata.
    weak_pendencias = _looks_weak_items(pendencias, min_good=2) or len(pendencias) < max(2, len(ativos) // 2)
    if weak_pendencias:
        pendencias.extend(ativos)

    return _dedupe_items(pendencias)


def _collect_deliberacoes(dados: dict[str, Any], atividades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deliberacoes: list[dict[str, Any]] = []
    for item in _as_list(dados.get("deliberacoes")):
        if isinstance(item, dict):
            deliberacoes.append(item)

    # Se a IA devolveu uma deliberação genérica/isolada, usa as atividades reais da ata.
    titulos_reais = [a for a in atividades if not _is_placeholder(_atividade_titulo(a))]
    delib_fracas = (not deliberacoes) or len(deliberacoes) < min(3, max(1, len(titulos_reais) // 4)) or _looks_weak_items(deliberacoes, min_good=2)
    if deliberacoes and not delib_fracas:
        return deliberacoes

    # Fallback: transformar atividades reais da ata em deliberações/açōes formais.
    output: list[dict[str, Any]] = []
    for item in atividades:
        output.append(
            {
                "titulo": _atividade_titulo(item),
                "descricao": _atividade_descricao(item),
                "decisao": _atividade_acao(item),
                "responsaveis": [_atividade_responsavel(item)],
                "prazo": _atividade_prazo(item),
                "tipo": _status_label(item.get("status")),
                "status": item.get("status"),
                "criticidade": item.get("criticidade"),
                "categoria": _atividade_categoria(item),
            }
        )
    return output


def _build_meta(obra: Obra, relatorio: RelatorioSemanal, dados: dict[str, Any], gpt3: dict[str, Any] | None = None) -> dict[str, Any]:
    gerais = _get_dados_gerais(dados)
    meta_gpt3 = _as_dict(_as_dict(gpt3).get("meta"))
    metricas = _as_dict(dados.get("metricas_resumo"))

    obra_nome = _text(gerais.get("obra") or meta_gpt3.get("project") or obra.nome, obra.nome)
    numero_ata = _text(gerais.get("numero_ata") or relatorio.numero_ata)
    ref = _date_br(gerais.get("data_referencia") or meta_gpt3.get("refDate") or relatorio.data_referencia)

    return {
        "project": obra_nome,
        "title": _text(meta_gpt3.get("title") or gerais.get("titulo"), "Relatório Semanal de Obra"),
        "rev": f"ATA {numero_ata}" if numero_ata else _text(meta_gpt3.get("rev")),
        "refDate": ref,
        "engineer": _text(gerais.get("engenheiro_responsavel") or meta_gpt3.get("engineer") or obra.engenheiro_responsavel, "Não informado"),
        "contractDeadline": _date_br(gerais.get("prazo_contratual") or meta_gpt3.get("contractDeadline") or obra.prazo_contratual),
        "workingDaysLeft": _text(gerais.get("dias_uteis_restantes") or meta_gpt3.get("workingDaysLeft"), "Não calculável"),
        "globalProgress": _progress(gerais.get("avanco_global") or metricas.get("avanco_global") or meta_gpt3.get("globalProgress")),
        "weeklyClosing": _text(gerais.get("fechamento") or meta_gpt3.get("weeklyClosing"), "Não informado"),
        "week": _text(gerais.get("semana_referencia") or meta_gpt3.get("week") or relatorio.data_referencia.strftime("Semana %U"), "Semana não informada"),
        "footerNote": _text(meta_gpt3.get("footerNote"), "Fechamento semanal toda quinta-feira · Envio ao cliente na sexta"),
    }


def _build_hero(dados: dict[str, Any], atividades: list[dict[str, Any]], pendencias: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    analise = _as_dict(dados.get("analise_executiva"))
    metricas = _as_dict(dados.get("metricas_resumo"))

    ativos = [a for a in atividades if normalizar_status(a.get("status")) not in {"concluido", "informativo"}]
    informativos = [a for a in atividades if normalizar_status(a.get("status")) == "informativo"]
    concluidos = [a for a in atividades if normalizar_status(a.get("status")) == "concluido"]
    altos = [a for a in atividades if _nivel_template(a.get("criticidade")) in {"critico", "alto"}]

    viabilidade = _text(analise.get("viabilidade_prazo_contratual"))
    pills: list[dict[str, str]] = []
    if viabilidade:
        tone = "crit" if viabilidade in {"inviavel", "em_risco"} else ""
        pills.append({"label": f"Viabilidade: {viabilidade}", "tone": tone})
    pills.extend(
        [
            {"label": f"Itens ativos: {len(ativos) or metricas.get('quantidade_frentes_atrasadas') or 0}", "tone": ""},
            {"label": f"Pendências: {len(pendencias)}", "tone": "warn" if pendencias else ""},
            {"label": f"Informativos: {len(informativos)}", "tone": ""},
            {"label": f"Críticos/altos: {len(altos)}", "tone": "crit" if altos else ""},
        ]
    )

    return {
        "headline": _text(analise.get("resumo_executivo_2_frases"), f"Relatório semanal da obra {meta['project']}"),
        "subheadline": _text(analise.get("diagnostico_geral"), "Atualização executiva consolidada."),
        "pills": pills[:5],
    }


def _build_section_texts(dados: dict[str, Any], pendencias: list[dict[str, Any]]) -> dict[str, str]:
    analise = _as_dict(dados.get("analise_executiva"))
    leitura = _as_dict(analise.get("leitura_gerencial"))
    return {
        "criticos": _text(analise.get("justificativa_viabilidade"), "Diagnóstico direto dos fatores que determinam a viabilidade da entrega. Ordenados por nível de criticidade."),
        "cronograma": _text("; ".join(analise.get("caminho_critico") or []), "Leitura consolidada de frentes, responsáveis, prazos, avanço e status executivo."),
        "ambientes": "Situação atual de cada frente com avanço, dependências e próximos passos.",
        "extraEscopo": "Intervenções técnicas identificadas em campo ou registradas em ata.",
        "pendenciasTitle": "Pendências TOOLS / Cliente / Projetistas / Fornecedores",
        "pendencias": f"{len(pendencias)} decisões, entregas ou liberações pendentes exigem acompanhamento.",
        "planoTitle": "Plano de Ação Semanal",
        "planoAcao": _text(leitura.get("recomendacao_da_gerenciadora"), "Ações comprometidas com responsável e prazo para a próxima semana."),
        "ata": "Resumo dos registros formais identificados na ata semanal.",
        "deliberacoesTitle": "Deliberações Consolidadas",
        "deliberacoes": "Visão executiva ordenada por criticidade. ! Crítico · → Em andamento · ○ Aberto · ✓ Concluído",
        "mudancasTitle": "Mudanças em Relação às Atas Anteriores",
        "mudancas": "Comparação com histórico normalizado: reprogramações, reincidências, itens novos e baixas identificadas.",
    }


def _build_critical_points(dados: dict[str, Any], atividades: list[dict[str, Any]], pendencias: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pontos = []
    for idx, item in enumerate(_as_list(dados.get("pontos_criticos")), start=1):
        if not isinstance(item, dict):
            continue
        pontos.append(
            {
                "id": _text(item.get("id"), f"{idx:02d}"),
                "title": _text(item.get("titulo") or item.get("title"), "Ponto crítico sem título"),
                "level": _nivel_template(item.get("nivel") or item.get("criticidade")),
                "body": _text(item.get("descricao_executiva") or item.get("descricao") or item.get("description")),
                "tags": _as_list(item.get("tags")),
                "action": _text(item.get("acao_obrigatoria") or item.get("acao_recomendada") or item.get("proximos_passos"), "Acompanhar responsável e prazo."),
            }
        )

    # Se os pontos críticos vieram genéricos ou muito menores que as pendências reais,
    # recalcula a partir dos itens ativos/recorrentes da ata.
    pontos_fracos = (not pontos) or _looks_weak_items([{"titulo": p.get("title"), "descricao": p.get("body")} for p in pontos], min_good=2)
    if pontos and len(pontos) < min(3, max(1, len(pendencias) // 5)):
        pontos_fracos = True
    if pontos and not pontos_fracos:
        return pontos[:7]

    pontos = []
    candidatos = pendencias or atividades
    def score(item: dict[str, Any]) -> tuple[int, int, int]:
        nivel = _nivel_template(item.get("criticidade"))
        n = {"critico": 4, "alto": 3, "moderado": 2, "baixo": 1}.get(nivel, 1)
        recorrente = 1 if item.get("item_recorrente") else 0
        reprogramado = 1 if item.get("houve_reprogramacao") else 0
        return (n, recorrente, reprogramado)

    ordenados = sorted([i for i in candidatos if isinstance(i, dict)], key=score, reverse=True)
    for idx, item in enumerate(ordenados[:7], start=1):
        prazo = _atividade_prazo(item)
        resp = _atividade_responsavel(item)
        tags = [_status_label(item.get("status")), f"Prazo: {prazo}", f"Responsável: {resp}"]
        if item.get("item_recorrente"):
            tags.append("Item recorrente")
        if item.get("houve_reprogramacao"):
            tags.append("Houve reprogramação")
        categoria = _atividade_categoria(item)
        if categoria:
            tags.append(categoria)
        pontos.append(
            {
                "id": _text(item.get("id") or item.get("id_item"), f"{idx:02d}"),
                "title": _atividade_titulo(item),
                "level": _nivel_template(item.get("criticidade")),
                "body": _atividade_descricao(item),
                "tags": tags,
                "action": _atividade_acao(item),
            }
        )
    return pontos


def _build_phases(dados: dict[str, Any], atividades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    explicit = []
    for item in _as_list(dados.get("cronograma_summary") or dados.get("phases")):
        if isinstance(item, dict):
            explicit.append(item)
    if explicit:
        return explicit

    ativos = [a for a in atividades if normalizar_status(a.get("status")) not in {"concluido", "informativo"}]
    informativos = [a for a in atividades if normalizar_status(a.get("status")) == "informativo"]
    concluidos = [a for a in atividades if normalizar_status(a.get("status")) == "concluido"]
    total = max(len(atividades), 1)
    atuais = [a for a in atividades if "atual" in _atividade_categoria(a).lower()]

    return [
        {"name": "Itens ativos", "progress": None, "note": f"{len(ativos)} itens pendentes/em andamento detectados na ata."},
        {"name": "Informativos formais", "progress": None, "note": f"{len(informativos)} registros informativos separados das pendências."},
        {"name": "Itens concluídos", "progress": round((len(concluidos) / total) * 100), "note": f"{len(concluidos)} itens concluídos ou baixados em ata."},
        {"name": "Itens da ata atual", "progress": None, "note": f"{len(atuais)} itens registrados na ata atual."},
    ]


def _build_schedule(dados: dict[str, Any], atividades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)

    cronograma = _as_list(dados.get("cronograma_executivo"))
    cronograma_rows: list[dict[str, Any]] = []
    if cronograma:
        for item in cronograma:
            if not isinstance(item, dict):
                continue
            titulo = _text(item.get("frente") or item.get("ambiente_ou_pacote") or item.get("titulo"), "Item do cronograma")
            cronograma_rows.append({**item, "titulo": titulo})

    use_cronograma = bool(cronograma_rows) and not _looks_weak_items(cronograma_rows, min_good=2)
    if use_cronograma:
        for item in cronograma_rows:
            group = _text(item.get("grupo") or item.get("categoria"), "Cronograma Executivo")
            rows_by_group[group].append(
                {
                    "item": _text(item.get("titulo"), "Item do cronograma"),
                    "resp": _text(item.get("responsavel"), "Indefinido"),
                    "start": _date_br(item.get("inicio")),
                    "end": _date_br(item.get("termino") or item.get("prazo_reprogramado") or item.get("prazo_vigente")),
                    "progress": _progress(item.get("avanco_percentual")),
                    "status": _status_template(item.get("status")),
                    "statusLabel": _status_label(item.get("status")),
                }
            )
    else:
        # Cronograma executivo deve refletir itens ativos/em andamento.
        # Concluídos e informativos aparecem nas abas Ata e Mudanças/Histórico, para não poluir o caminho operacional.
        for item in atividades:
            status = normalizar_status(item.get("status"))
            if status in {"informativo", "concluido"}:
                continue
            group = _atividade_categoria(item)
            rows_by_group[group].append(
                {
                    "item": _atividade_titulo(item),
                    "resp": _atividade_responsavel(item),
                    "start": _date_br(item.get("data_abertura") or item.get("inicio")),
                    "end": _atividade_prazo(item),
                    "progress": _progress(item.get("avanco_percentual")),
                    "status": _status_template(item.get("status")),
                    "statusLabel": _status_label(item.get("status")),
                }
            )

    return [{"group": group, "rows": rows} for group, rows in rows_by_group.items() if rows]


def _build_ambientes(dados: dict[str, Any], atividades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for item in _as_list(dados.get("status_por_ambiente")):
        if not isinstance(item, dict):
            continue
        bullets = []
        bullets.extend(_as_list(item.get("pontos_realizados")))
        bullets.extend(_as_list(item.get("pendencias")))
        bullets.extend(_as_list(item.get("proximos_passos")))
        output.append(
            {
                "name": _text(item.get("ambiente"), "Ambiente não informado"),
                "meta": _text(item.get("onda_ou_grupo"), "Status por ambiente"),
                "progress": _progress(item.get("avanco_percentual")),
                "bullets": [str(b) for b in bullets[:6]],
            }
        )
    if output:
        return output

    grupos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in atividades:
        status = normalizar_status(item.get("status"))
        if status in {"informativo", "concluido"}:
            continue
        key = _text(item.get("ambiente") or item.get("empresa_responsavel") or item.get("responsavel") or item.get("categoria"), "Frente sem responsável")
        grupos[key].append(item)

    for key, itens in grupos.items():
        progresses = [_progress(i.get("avanco_percentual")) for i in itens if _progress(i.get("avanco_percentual")) is not None]
        prog = round(sum(progresses) / len(progresses)) if progresses else None
        output.append(
            {
                "name": f"Frente inferida: {key}",
                "meta": f"Ambiente/frente inferido a partir da ata • {len(itens)} item(ns) ativo(s)",
                "progress": prog,
                "bullets": [_atividade_titulo(i) for i in itens[:6]],
            }
        )
    return output


def _build_extra(dados: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    items = []
    for idx, item in enumerate(_as_list(dados.get("extra_escopo")), start=1):
        if not isinstance(item, dict):
            continue
        title = _text(item.get("titulo") or item.get("title"))
        body = _text(item.get("descricao") or item.get("motivo") or item.get("impacto") or item.get("body"))
        if not title and not body:
            continue
        items.append(
            {
                "id": _text(item.get("id"), f"{idx:02d}"),
                "title": title or "Extra-escopo",
                "body": body,
                "tags": [t for t in [_text(item.get("responsavel")), _text(item.get("observacao_contratual"))] if t],
            }
        )
    note = ""
    if items:
        note = "Itens fora do check-list devem ser formalizados quando houver impacto contratual, prazo ou custo."
    return items, note


def _build_pendencias_tools(pendencias: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for idx, item in enumerate(pendencias, start=1):
        title = _text(item.get("titulo") or item.get("title"), _atividade_titulo(item))
        prazo = _atividade_prazo(item)
        desc = _text(item.get("descricao") or item.get("desc") or _atividade_descricao(item))
        if prazo != INFORMACAO_NAO_INFORMADA and "Prazo" not in desc:
            desc = f"{desc} Prazo vigente: {prazo}."
        output.append(
            {
                "id": f"{idx:02d}",
                "title": title,
                "desc": desc,
                "area": _text(item.get("ambiente") or item.get("area") or item.get("categoria") or item.get("fonte"), _atividade_categoria(item)),
                "level": _level_label(item.get("criticidade") or item.get("prioridade") or item.get("level")),
            }
        )
    return output


def _build_plano(dados: dict[str, Any], pontos: list[dict[str, Any]], pendencias: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for idx, item in enumerate(_as_list(dados.get("plano_acao")), start=1):
        if not isinstance(item, dict):
            continue
        output.append(
            {
                "id": f"{idx:02d}",
                "title": _text(item.get("titulo") or item.get("title"), "Ação semanal"),
                "body": _text(item.get("descricao") or item.get("resultado_esperado") or item.get("body")),
                "meta": " · ".join([p for p in [_text(item.get("responsavel")), _date_br(item.get("prazo"), "")] if p]),
                "level": _text(item.get("prioridade") or item.get("level"), "Média"),
            }
        )
    # Se o plano veio genérico ou curto demais, constrói a partir das pendências reais.
    plano_fraco = (not output) or len(output) < min(3, max(1, len(pendencias) // 3)) or _looks_weak_items(output, min_good=2)
    generic_titles = {"acompanhamento das aprovações", "plano de ação", "acao semanal", "ação semanal"}
    if output and any(_norm_key(item.get("title")) in generic_titles for item in output):
        plano_fraco = True
    if output and not plano_fraco:
        return output

    base = pontos or _build_pendencias_tools(pendencias)
    output = []
    for idx, item in enumerate(base[:8], start=1):
        output.append(
            {
                "id": f"{idx:02d}",
                "title": _text(item.get("title") or item.get("titulo")),
                "body": _text(item.get("action") or item.get("desc") or item.get("descricao"), "Acompanhar evolução na próxima reunião."),
                "meta": " · ".join([p for p in [_text(item.get("responsavel") or item.get("responsible")), _text(item.get("deadline") or item.get("prazo"))] if p]) or "Responsável/prazo conforme ata",
                "level": _level_label(item.get("level") or item.get("criticidade")),
            }
        )
    return output


def _build_ata(deliberacoes: list[dict[str, Any]], atividades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source = deliberacoes or atividades
    output = []
    for idx, item in enumerate(source[:20], start=1):
        if not isinstance(item, dict):
            continue
        responsaveis = item.get("responsaveis")
        if isinstance(responsaveis, list):
            responsavel = ", ".join(str(r) for r in responsaveis if r)
        else:
            responsavel = _text(responsaveis or item.get("responsavel") or item.get("responsavel_pendencia"))
        prazo = _date_br(item.get("prazo") or item.get("prazo_vigente") or item.get("prazo_limite"))
        decisao = _text(item.get("decisao") or item.get("decision") or _atividade_acao(item))
        if decisao == "Acompanhar responsável e prazo vigente." and responsavel:
            decisao = f"Acompanhar atendimento por {responsavel} até {prazo}."
        output.append(
            {
                "id": idx,
                "tag": _text(item.get("tipo") or item.get("tag") or _status_label(item.get("status")), "Registro"),
                "title": _text(item.get("titulo") or item.get("title"), _atividade_titulo(item)),
                "body": _text(item.get("descricao") or item.get("body") or _atividade_descricao(item)),
                "decision": decisao,
            }
        )
    return output


def _build_deliberacoes(deliberacoes: list[dict[str, Any]], ata_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    source = deliberacoes if deliberacoes else ata_items
    for item in source[:20]:
        if not isinstance(item, dict):
            continue
        titulo = _text(item.get("titulo") or item.get("title"), _text(item.get("text")))
        texto = _text(item.get("text") or item.get("decisao") or item.get("decision") or item.get("descricao") or item.get("body"))
        if titulo and texto and not texto.startswith(titulo):
            texto = f"{titulo}: {texto}"
        responsaveis = item.get("responsaveis")
        if isinstance(responsaveis, list):
            responsavel = ", ".join(str(r) for r in responsaveis if r)
        else:
            responsavel = _text(responsaveis or item.get("responsavel"), "Indefinido")
        prazo = _date_br(item.get("prazo") or item.get("deadline"), "Não informado")
        output.append(
            {
                "mark": _text(item.get("mark"), _mark_for_status(item.get("status") or item.get("tipo"), item.get("criticidade"))),
                "text": texto,
                "meta": _text(item.get("meta"), f"{responsavel} · {prazo}"),
            }
        )
    return output




def _as_title_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, dict):
            txt = _text(item.get("titulo") or item.get("title") or item.get("descricao") or item.get("description"))
        else:
            txt = _text(item)
        if txt:
            out.append(txt)
    return out


def _build_historico_mudancas(dados: dict[str, Any], atividades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Monta a seção final de mudanças x histórico.

    O histórico normalizado deve ser usado para comparação; quando o GPT2 informar
    reprogramações, itens novos, concluídos ou sem evolução, essa seção registra as
    mudanças abaixo do relatório sem misturar com as pendências operacionais.
    """
    output: list[dict[str, str]] = []
    comp = _as_dict(dados.get("comparacao_historica"))

    groups = [
        ("Novos", "Itens novos identificados na ata atual", comp.get("itens_novos")),
        ("Concluídos", "Itens concluídos ou baixados em relação ao histórico", comp.get("itens_concluidos")),
        ("Reprogramados", "Itens com alteração de prazo em relação ao histórico", comp.get("itens_reprogramados")),
        ("Sem evolução", "Itens recorrentes que permanecem sem avanço real", comp.get("itens_sem_evolucao")),
        ("Atraso reincidente", "Itens com reincidência de atraso ou múltiplas reprogramações", comp.get("itens_com_atraso_reincidente")),
        ("Risco aumentado", "Itens com aumento de criticidade ou impacto", comp.get("itens_com_risco_aumentado")),
        ("Risco reduzido", "Itens com redução de criticidade ou impacto", comp.get("itens_com_risco_reduzido")),
    ]
    for tipo, descricao, value in groups:
        for titulo in _as_title_list(value):
            output.append({"type": tipo, "title": titulo, "description": descricao, "meta": "Comparação histórica"})

    persist = _as_dict(dados.get("dados_para_persistencia"))
    for item in _as_list(persist.get("historico_item_status")):
        if not isinstance(item, dict):
            continue
        title = _text(item.get("titulo_item") or item.get("titulo"))
        if not title:
            continue
        status_ant = _text(item.get("status_anterior"), "Não informado")
        status_atual = _text(item.get("status_atual"), "Não informado")
        crit_ant = _text(item.get("criticidade_anterior"))
        crit_atual = _text(item.get("criticidade_atual"))
        comentario = _text(item.get("comentario_evolucao"))
        desc = comentario or f"Status: {status_ant} → {status_atual}."
        meta = " · ".join([p for p in [f"Criticidade: {crit_ant} → {crit_atual}" if crit_ant or crit_atual else "", f"Prazo: {_text(item.get('prazo_anterior'))} → {_text(item.get('prazo_atual'))}" if item.get("prazo_anterior") or item.get("prazo_atual") else ""] if p])
        output.append({"type": "Status", "title": title, "description": desc, "meta": meta or "Histórico de status"})

    for item in _as_list(persist.get("reprogramacoes_prazo")):
        if not isinstance(item, dict):
            continue
        title = _text(item.get("titulo_item") or item.get("titulo"))
        if not title:
            continue
        prazo_ant = _date_br(item.get("prazo_anterior"), _text(item.get("prazo_anterior"), "Não informado"))
        prazo_novo = _date_br(item.get("prazo_novo"), _text(item.get("prazo_novo"), "Não informado"))
        desc = _text(item.get("motivo_reprogramacao") or item.get("impacto"), f"Prazo reprogramado de {prazo_ant} para {prazo_novo}.")
        output.append({"type": "Reprogramação", "title": title, "description": desc, "meta": f"{prazo_ant} → {prazo_novo}"})

    # Fallback determinístico a partir da própria ata: mesmo sem histórico externo,
    # a tabela da ata já traz data-item, ata de origem, reprogramações, incidência,
    # status concluído e itens novos da ata atual.
    for item in atividades:
        if not isinstance(item, dict):
            continue
        status_norm = normalizar_status(item.get("status"))
        secao_norm = _norm_key(_atividade_categoria(item))
        ata_origem = _text(item.get("numero_ata_origem"))
        data_item = _date_br(item.get("data_abertura"), _text(item.get("data_abertura"), "Não informado"))

        if item.get("historico_secao") == "atuais" or "ata atual" in secao_norm:
            output.append(
                {
                    "type": "Novo / ATA atual",
                    "title": _atividade_titulo(item),
                    "description": _atividade_descricao(item),
                    "meta": f"ATA {ata_origem or 'atual'} · Data item: {data_item} · Status: {_status_label(item.get('status'))}",
                }
            )

        if status_norm == "concluido":
            output.append(
                {
                    "type": "Concluído",
                    "title": _atividade_titulo(item),
                    "description": _text(item.get("observacoes"), _atividade_descricao(item)),
                    "meta": f"Baixado/concluído · Prazo/registro: {_atividade_prazo(item)}",
                }
            )
        elif status_norm == "informativo":
            output.append(
                {
                    "type": "Informativo",
                    "title": _atividade_titulo(item),
                    "description": _atividade_descricao(item),
                    "meta": f"Registro formal · ATA {ata_origem or 'não informada'}",
                }
            )

        if item.get("houve_reprogramacao"):
            dates = item.get("datas_lidas") if isinstance(item.get("datas_lidas"), list) else []
            prazo_ant = dates[-2] if len(dates) >= 2 else _text(item.get("prazo_original"), "Não informado")
            prazo_novo = _atividade_prazo(item)
            output.append(
                {
                    "type": "Reprogramação",
                    "title": _atividade_titulo(item),
                    "description": _text(item.get("observacoes"), "Item com prazo alterado em relação às atas anteriores."),
                    "meta": f"{prazo_ant} → {prazo_novo}",
                }
            )
        elif item.get("item_recorrente") and normalizar_status(item.get("status")) not in {"concluido", "informativo"}:
            output.append(
                {
                    "type": "Recorrente",
                    "title": _atividade_titulo(item),
                    "description": _text(item.get("observacoes"), "Item permanece aberto em relação ao histórico anterior."),
                    "meta": f"Prazo vigente: {_atividade_prazo(item)}",
                }
            )

    # Deduplica mantendo ordem e limita para não tornar o relatório excessivamente longo.
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for item in output:
        key = f"{_norm_key(item.get('type'))}|{_norm_key(item.get('title'))}|{_norm_key(item.get('meta'))}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:60]


def _merge_with_gpt3(base: dict[str, Any], gpt3: dict[str, Any] | None) -> dict[str, Any]:
    """Preserva dados determinísticos. Usa GPT3 apenas para enriquecer textos vazios, nunca para esvaziar listas."""
    if not isinstance(gpt3, dict):
        return base

    merged = dict(base)
    for key in ["meta", "hero", "sectionTexts", "criticalAlert", "quality"]:
        if isinstance(gpt3.get(key), dict):
            current = dict(merged.get(key) or {})
            for sub_key, value in gpt3[key].items():
                if current.get(sub_key) in (None, "", [], {}) and value not in (None, "", [], {}):
                    current[sub_key] = value
            merged[key] = current

    # Listas do GPT3 só entram quando o adaptador não conseguiu montar nada relevante.
    for key in ["criticalPoints", "phases", "schedule", "ambientes", "extraEscopo", "pendenciasTools", "planoAcao", "ata", "deliberacoes", "historicoMudancas"]:
        if not merged.get(key) and isinstance(gpt3.get(key), list):
            merged[key] = gpt3[key]

    return merged


def build_report_json_from_gpt2(
    obra: Obra,
    relatorio: RelatorioSemanal,
    dados_gpt2: dict[str, Any],
    dados_gpt3: dict[str, Any] | None = None,
    dados_gpt1: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Monta o JSON final do template a partir do GPT2, com fallback no GPT3.

    Motivo: o GPT3 pode resumir demais e devolver arrays vazios. O GPT2 também pode perder
    títulos quando a ata veio visual/escaneada. Por isso o adaptador usa GPT2 + GPT1/OCR
    validado e preserva todos os itens estruturados antes da renderização.
    """
    dados = dados_gpt2 or {}
    atividades = _collect_atividades(dados, dados_gpt1)
    pendencias = _collect_pendencias(dados, atividades)
    deliberacoes = _collect_deliberacoes(dados, atividades)

    meta = _build_meta(obra, relatorio, dados, dados_gpt3)
    pontos = _build_critical_points(dados, atividades, pendencias)
    extra, extra_note = _build_extra(dados)
    ata_items = _build_ata(deliberacoes, atividades)

    alert_title = pontos[0]["title"] if pontos else "Atenção aos itens de maior recorrência"
    alert_body = pontos[0]["body"] if pontos else "A criticidade considera prazo, status, incidência/SLA e reprogramações identificadas na ata."

    report = {
        "meta": meta,
        "hero": _build_hero(dados, atividades, pendencias, meta),
        "sectionTexts": _build_section_texts(dados, pendencias),
        "criticalAlert": {"title": alert_title, "body": alert_body},
        "criticalPoints": pontos,
        "phases": _build_phases(dados, atividades),
        "schedule": _build_schedule(dados, atividades),
        "ambientes": _build_ambientes(dados, atividades),
        "extraEscopo": extra,
        "extraEscopoNote": extra_note,
        "pendenciasTools": _build_pendencias_tools(pendencias),
        "planoAcao": _build_plano(dados, pontos, pendencias),
        "ata": ata_items,
        "deliberacoes": _build_deliberacoes(deliberacoes, ata_items),
        "historicoMudancas": _build_historico_mudancas(dados, atividades),
        "quality": {
            "ocrLevel": _text(_as_dict(dados.get("quality")).get("ocrLevel") or _as_dict(dados.get("dados_documento")).get("qualidade_visual")),
            "corrections": _as_list(dados.get("correcoes_contextuais")),
            "warnings": _as_list(dados.get("alertas_qualidade") or dados.get("alertas")),
            "dataGaps": [],
            "sources": [],
        },
    }
    return _merge_with_gpt3(report, dados_gpt3)
