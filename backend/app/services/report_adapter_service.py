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


def _ata_norm(value: Any) -> str:
    """Normaliza número de ata para comparação: 004, 0004 e ATA 004 viram 4."""
    txt = _text(value)
    if not txt:
        return ""
    nums = re.findall(r"\d+", txt)
    if not nums:
        return _norm_key(txt) if "_norm_key" in globals() else txt.strip().lower()
    try:
        return str(int(nums[-1]))
    except ValueError:
        return nums[-1].lstrip("0") or "0"


def _ata_equal(left: Any, right: Any) -> bool:
    l_norm = _ata_norm(left)
    r_norm = _ata_norm(right)
    return bool(l_norm and r_norm and l_norm == r_norm)


def _parse_date_any(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    parsed = safe_date(value)
    if parsed:
        return parsed
    txt = _text(value)
    if txt:
        m = _DATE_RE.search(txt) if "_DATE_RE" in globals() else re.search(r"\b\d{2}/\d{2}/\d{4}\b", txt)
        if m:
            return safe_date(m.group(0))
    return None


def _calculate_period_progress(start_value: Any, end_value: Any, reference_value: Any, fallback: Any = None) -> int | None:
    """Calcula avanço por janela de datas: início/data item -> prazo/término, na data de referência."""
    explicit = _progress(fallback)
    start = _parse_date_any(start_value)
    end = _parse_date_any(end_value)
    reference = _parse_date_any(reference_value)
    if not (start and end and reference):
        return explicit
    if end <= start:
        return 100 if reference >= end else 0
    if reference <= start:
        return 0
    if reference >= end:
        return 100
    total_days = max((end - start).days, 1)
    elapsed_days = max((reference - start).days, 0)
    return int(max(0, min(100, round((elapsed_days / total_days) * 100))))


_DATE_RE = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
_STATUS_RE = re.compile(r"\b(Em\s+andamento|Conclu[ií]da|Conclu[ií]do|Informação|Informacao|Pendente|Atrasada|Bloqueante)\b", re.IGNORECASE)
_ROW_START_RE = re.compile(r"(?m)^\s*(\d{1,3})\s+(\d{3})\s+(\d{2}/\d{2}/\d{4})\s+(.*)$")
_SECTION_ALIASES = {
    "pendentes": "Itens Ata Anterior / Itens Pendentes",
    "atuais": "Itens Ata Atual",
    "concluidos": "Itens Concluídos e Informativos",
}


def _all_dates(text: str) -> list[str]:
    return _DATE_RE.findall(text or "")


def _compact_text(value: Any, max_len: int | None = None) -> str:
    """Normaliza quebras de linha/espacos para textos de card e evita blocos ilegíveis."""
    txt = _text(value)
    if not txt:
        return ""
    txt = re.sub(r"\s+", " ", txt).strip()
    # Remove ruídos típicos que aparecem quando o OCR cola cabeçalho/rodapé na última linha.
    txt = re.sub(r"\s+Disciplina\s+E-mail\s+.*$", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\s+ATA DE REUNIÃO\s+-.*$", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\s+---\s*Página\s+\d+\s*---.*$", "", txt, flags=re.IGNORECASE)
    if max_len and len(txt) > max_len:
        txt = txt[: max_len - 1].rstrip() + "…"
    return txt


def _fix_title_by_body(titulo: str, body: str) -> str:
    """Corrige títulos repetidos quando o OCR mantém o cabeçalho errado, como mapa civil x instalações."""
    title_key = _norm_key(titulo) if "_norm_key" in globals() else titulo.lower()
    body_key = _norm_key(body) if "_norm_key" in globals() else body.lower()
    if "mapa mao de obra civil" in title_key and ("instalacoes eletricas" in body_key or "hidraulicas" in body_key):
        return "Mapa de instalações elétricas e hidráulicas"
    return titulo


def _canonical_category_value(value: Any) -> str:
    """Padroniza nomes de seção para não duplicar itens iguais por rótulos diferentes."""
    raw = _text(value, "Itens da Semana")
    key = _norm_key(raw)
    if "concluido" in key or "concluidos" in key or "informativo" in key:
        return "Itens Concluídos e Informativos"
    if "ata atual" in key or key in {"itens atuais", "atuais", "itens atual"}:
        return "Itens Ata Atual"
    if "ata anterior" in key or "pendente" in key or key in {"itens pendentes", "pendentes"}:
        return "Itens Ata Anterior / Itens Pendentes"
    return raw


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
            if re.search(r"^(Disciplina|Construtora\s+\S+@|ATA DE REUNIÃO|Cliente / Obra|Gerenciamento\s+\S+@|---\s*Página|\[)", ln, re.IGNORECASE):
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
        titulo = _fix_title_by_body(titulo, body)
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
                "descricao": _compact_text(descricao, 700),
                "observacoes": _compact_text(observacao, 900),
                "evidencia": _compact_text(block, 1400),
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

    # Prioridade máxima para o texto bruto dos arquivos. Ele preserva melhor a tabela.
    # Não concatenar texto bruto + texto_validado: isso duplicava a ata e contaminava o
    # corpo dos itens com linhas repetidas, fazendo o relatório 7 quebrar/ficar ilegível.
    raw_texts: list[str] = []
    for key in ["arquivos_contexto_extraido", "files_context_text", "texto_bruto_arquivos"]:
        txt = _text(extracao.get(key))
        if txt:
            raw_texts.append(txt)

    fallback_texts: list[str] = []
    for key in ["texto_validado", "texto_extraido", "raw_text", "conteudo_textual"]:
        txt = _text(extracao.get(key))
        if txt:
            fallback_texts.append(txt)

    if not raw_texts:
        for tabela in _as_list(extracao.get("tabelas_identificadas")):
            if not isinstance(tabela, dict):
                continue
            linhas = tabela.get("linhas")
            if isinstance(linhas, list) and linhas:
                fallback_texts.append("\n".join(str(l) for l in linhas))

    texts = raw_texts or fallback_texts
    parsed: list[dict[str, Any]] = []
    for text in texts:
        sections = _split_ocr_sections(text)
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
    ]
    texto = " ".join(p for p in partes if p).strip()
    # Evidência é usada só quando não existe descrição; colocar a evidência junto
    # deixava o card com a linha inteira da tabela duplicada.
    if not texto:
        texto = _text(item.get("evidencia"))
    return _compact_text(texto, 900) or "Registro da ata para acompanhamento."


def _split_historico_atualizacoes(value: Any) -> list[str]:
    """Separa observações de ata em tópicos por data (05.05, 12.05, 19.05...)."""
    txt = _compact_text(value, 1400)
    if not txt:
        return []
    parts = re.split(r"(?=\b\d{2}\.\d{2}\s*-)", txt)
    updates = []
    for part in parts:
        part = part.strip(" ;")
        if re.match(r"^\d{2}\.\d{2}\s*-", part):
            updates.append(part.rstrip(" .") + ".")
    return updates


def _strip_update_date(value: str) -> str:
    return re.sub(r"^\s*\d{2}\.\d{2}\s*-\s*", "", value or "").strip()


def _verbo_para_infinitivo(frase: str) -> str:
    replacements = [
        (r"^Cateo\s+enviar[áa]", "CATEO enviar"),
        (r"^A\s+Cateo\s+enviar[áa]", "CATEO enviar"),
        (r"^Cateo\s+realizar[áa]", "CATEO realizar"),
        (r"^A\s+Cateo\s+realizar[áa]", "CATEO realizar"),
        (r"^Cateo\s+atualizar[áa]", "CATEO atualizar"),
        (r"^A\s+Cateo\s+atualizar[áa]", "CATEO atualizar"),
        (r"^Projetista\s+enviar[áa]", "projetista enviar"),
        (r"^Arquitetura\s+realizar[áa]", "arquitetura realizar"),
        (r"^Cliente\s+retirar[áa]?", "cliente retirar"),
    ]
    out = frase.strip()
    for pattern, repl in replacements:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return out


def _atividade_corpo_executivo(item: dict[str, Any]) -> str:
    """Corpo do card: descrição base + histórico em tópicos quando houver."""
    base = _compact_text(item.get("descricao") or item.get("description"), 700)
    if not base:
        base = _compact_text(item.get("evidencia"), 700) or "Registro da ata para acompanhamento."

    historico_txt = _text(item.get("observacoes") or item.get("observacao") or item.get("historico_cronologico"))
    updates = _split_historico_atualizacoes(historico_txt)
    if not updates:
        return base

    bullets = "\n".join(f"• {update}" for update in updates)
    return f"{base}\n\nAtualizações:\n{bullets}"


def _atividade_acao(item: dict[str, Any]) -> str:
    """Gera ação curta e executiva, evitando repetir todo o histórico do card."""
    explicit = _compact_text(item.get("proximos_passos") or item.get("acao_recomendada"), 240)
    if explicit and len(_split_historico_atualizacoes(explicit)) <= 1:
        return explicit

    observacao = _text(item.get("observacoes") or item.get("observacao") or item.get("historico_cronologico"))
    updates = _split_historico_atualizacoes(observacao)
    latest = _strip_update_date(updates[-1]) if updates else _compact_text(observacao, 240)
    prazo = _atividade_prazo(item)
    responsavel = _atividade_responsavel(item)

    if latest:
        lower = latest.lower()
        if lower.startswith("aguardando"):
            return latest.rstrip(".") + "."
        if any(word in lower for word in ["enviará", "enviara", "realizará", "realizara", "atualizará", "atualizara"]):
            action = _verbo_para_infinitivo(latest)
            if not action.lower().startswith("aguardando"):
                action = f"Aguardando {action[0].lower() + action[1:] if action else action}"
            return action.rstrip(".") + "."
        if "aprov" in lower and "cliente" in lower:
            return latest.rstrip(".") + "."
        if len(latest) <= 180:
            return latest.rstrip(".") + "."

    if prazo != INFORMACAO_NAO_INFORMADA:
        return f"Acompanhar {responsavel} para atendimento até {prazo}."
    return "Acompanhar responsável e prazo vigente."


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
    return _canonical_category_value(item.get("categoria") or item.get("secao") or item.get("grupo") or item.get("ambiente") or "Itens da Semana")


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
    score = 0
    for key in ["titulo", "title", "descricao", "description", "observacoes", "observacao", "historico_cronologico", "prazo_vigente", "prazo", "termino", "responsavel", "empresa_responsavel", "criticidade", "status"]:
        if _text(item.get(key)):
            score += 1
    if not _is_placeholder(_atividade_titulo(item)):
        score += 8
    if _text(item.get("descricao") or item.get("description")):
        score += 4
    if _text(item.get("fonte")).upper() in {"PDF/OCR", "PDF", "OCR"}:
        score += 6
    if _norm_key(_atividade_categoria(item)) in {
        _norm_key("Itens Ata Atual"),
        _norm_key("Itens Ata Anterior / Itens Pendentes"),
        _norm_key("Itens Concluídos e Informativos"),
    }:
        score += 3
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
    status = _norm_key(normalizar_status(item.get("status")) or item.get("status"))
    secao = _norm_key(_atividade_categoria(item))
    numero_ata = _ata_norm(item.get("numero_ata_origem"))
    numero_item = _text(item.get("numero_item"))
    if numero_ata and numero_item:
        return f"ata:{numero_ata}|item:{numero_item}|{status}"
    if _is_placeholder(titulo):
        prazo = _norm_key(_atividade_prazo(item))
        return f"{titulo}|{secao}|{prazo}|{status}|{_norm_key(_atividade_descricao(item))[:80]}"
    # Para mesclar itens iguais vindos do GPT2 e do OCR, não use prazo como chave:
    # versões pobres frequentemente vêm sem prazo e duplicavam as linhas enriquecidas.
    return f"{titulo}|{status}"


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

    first_pass = [merged[k] for k in order]

    # Segunda passada: elimina duplicidades entre itens pobres vindos do GPT
    # e itens completos reconstruídos pelo OCR. O primeiro merge por
    # número de ata/item é conservador; esta etapa junta registros com
    # mesmo título + status, priorizando o item que tem Nº Ata/Data Item/Prazo.
    by_title_status: dict[str, dict[str, Any]] = {}
    order2: list[str] = []
    for item in first_pass:
        title = _norm_key(_atividade_titulo(item))
        status = _norm_key(normalizar_status(item.get("status")) or item.get("status"))
        if not title or _is_placeholder(title):
            title = _norm_key(_atividade_descricao(item))[:80]
        key = f"{title}|{status}"
        if key not in by_title_status:
            by_title_status[key] = item
            order2.append(key)
        else:
            by_title_status[key] = _merge_item(by_title_status[key], item)
    return [by_title_status[k] for k in order2]


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
        "categoria": _canonical_category_value(secao),
        "secao": _canonical_category_value(secao),
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
        # Quando o OCR encontrou a tabela formal da ATA, ele passa a ser a fonte autoritativa
        # para contagens, cronograma e pendências. Isso evita duplicar itens vindos do GPT2
        # em grupos genéricos como "Cronograma Executivo".
        secoes_formais = {_canonical_category_value(a.get("categoria") or a.get("secao")) for a in atividades_gpt1}
        tem_tabela_formal = len(atividades_gpt1) >= 8 and any("Ata Atual" in secao for secao in secoes_formais)
        if tem_tabela_formal:
            atividades = list(atividades_gpt1)
        else:
            atividades.extend(atividades_gpt1)

    atividades = _dedupe_items(atividades)

    # Se o GPT2 retornou itens genéricos, descarte placeholders quando houver itens reais do GPT1.
    if atividades_gpt1 and _looks_weak_items([a for a in atividades if a not in atividades_gpt1], min_good=2):
        atividades = _dedupe_items(atividades_gpt1 + [a for a in atividades if not _is_placeholder(_atividade_titulo(a))])

    # Normaliza a seção após mesclagem, remove itens efetivamente vazios e deduplica de novo.
    normalizadas: list[dict[str, Any]] = []
    for item in atividades:
        if not isinstance(item, dict) or _is_placeholder(_atividade_titulo(item)):
            continue
        item = dict(item)
        categoria = _atividade_categoria(item)
        item["categoria"] = categoria
        item["secao"] = categoria
        normalizadas.append(item)

    return _dedupe_items(normalizadas)


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
        "criticos": "Todos os itens da ata com status Em andamento, organizados com responsável, prazo e ação obrigatória.",
        "cronograma": "Itens da ata atual, com início pela coluna Data Item, término pelo prazo e avanço calculado pela janela de datas.",
        "ambientes": "Consolidação dos itens por responsável, separando ações em aberto, informações, concluídas e prazos críticos.",
        "extraEscopo": "Classificação das pendências por impacto em prazo, custo, projeto/definição e documentação/contratos.",
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
    """Primeira aba do relatório: Pendências.

    Regra visual solicitada: trazer todos os itens cujo Status da ATA seja
    "Em andamento", não apenas os pontos críticos/altos.
    """
    candidatos = [item for item in atividades if isinstance(item, dict) and normalizar_status(item.get("status")) == "andamento"]
    if not candidatos:
        candidatos = [item for item in pendencias if isinstance(item, dict) and normalizar_status(item.get("status")) == "andamento"]

    pontos: list[dict[str, Any]] = []
    for idx, item in enumerate(candidatos, start=1):
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
                "body": _atividade_corpo_executivo(item),
                "tags": tags,
                "action": _atividade_acao(item),
            }
        )
    return pontos

def _is_item_da_ata_atual(item: dict[str, Any], current_ata: Any = None) -> bool:
    """Retorna True somente quando a coluna Nº Ata do item bate com a ata processada."""
    return bool(current_ata and _ata_equal(item.get("numero_ata_origem"), current_ata))


def _build_phases(dados: dict[str, Any], atividades: list[dict[str, Any]], current_ata: Any = None) -> list[dict[str, Any]]:
    # A aba 2 deve refletir apenas os itens cujo Nº Ata corresponde à ata digitada/processada.
    atuais = [a for a in atividades if isinstance(a, dict) and _is_item_da_ata_atual(a, current_ata)]
    informativos = [a for a in atuais if normalizar_status(a.get("status")) == "informativo"]
    concluidos = [a for a in atuais if normalizar_status(a.get("status")) == "concluido"]
    andamento = [a for a in atuais if normalizar_status(a.get("status")) == "andamento"]
    total = len(atuais)
    total_base = max(total, 1)
    percent_concluidos = round((len(concluidos) / total_base) * 100) if total else 0

    return [
        {
            "name": "Itens da ata atual",
            "value": str(total),
            "progress": None,
            "note": "Contagem dos itens cujo Nº Ata corresponde à ata processada.",
        },
        {
            "name": "Itens informação",
            "value": str(len(informativos)),
            "progress": None,
            "note": "Quantidade de itens da ata atual com status Informação.",
        },
        {
            "name": "Itens concluídos",
            "value": f"{percent_concluidos}%",
            "progress": percent_concluidos,
            "note": f"{len(concluidos)} itens concluídos com base em {total} item(ns) da ata atual.",
        },
        {
            "name": "Em andamento",
            "value": str(len(andamento)),
            "progress": None,
            "note": "Itens da ata atual com status Em andamento.",
        },
    ]


def _schedule_group_for_item(item: dict[str, Any]) -> str:
    titulo = _norm_key(_atividade_titulo(item))
    descricao = _norm_key(_atividade_descricao(item))
    combined = f"{titulo} {descricao}"
    if any(word in combined for word in ["art", "contrato", "assinatura", "fornecedor", "pagamento", "sinal"]):
        return "CONTRATOS E ARTS"
    if any(word in combined for word in ["cronograma"]):
        return "CRONOGRAMA"
    if any(word in combined for word in ["mapa", "mao de obra", "instalacoes eletricas", "hidraulicas"]):
        return "CONTRATAÇÕES E MAPAS"
    if any(word in combined for word in ["projeto", "arquitetura", "definicao", "definicoes"]):
        return "PROJETOS E DEFINIÇÕES"
    if any(word in combined for word in ["demolicao", "caixilho", "revestimento", "estanqueidade", "moveis", "garagem"]):
        return "DEMOLIÇÃO"
    return "OUTROS ITENS DA ATA"


def _build_schedule(dados: dict[str, Any], atividades: list[dict[str, Any]], current_ata: Any = None, reference_date: Any = None) -> list[dict[str, Any]]:
    """Cronograma da ATA: somente itens cuja coluna Nº Ata corresponde à ata atual, agrupados por tema."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    group_order = [
        "PROJETOS E DEFINIÇÕES",
        "DEMOLIÇÃO",
        "CONTRATOS E ARTS",
        "CRONOGRAMA",
        "CONTRATAÇÕES E MAPAS",
        "OUTROS ITENS DA ATA",
    ]

    current_items = [item for item in atividades if isinstance(item, dict) and _is_item_da_ata_atual(item, current_ata)]
    current_items.sort(key=lambda item: int(_text(item.get("numero_item"), "999") or 999) if str(_text(item.get("numero_item"), "999")).isdigit() else 999)

    for item in current_items:
        start_value = item.get("data_abertura") or item.get("inicio")
        end_value = item.get("prazo_vigente") or item.get("prazo") or item.get("termino") or item.get("prazo_limite")
        grouped[_schedule_group_for_item(item)].append(
            {
                "item": _atividade_titulo(item),
                "resp": _atividade_responsavel(item),
                "start": _date_br(start_value),
                "end": _date_br(end_value),
                "progress": _calculate_period_progress(start_value, end_value, reference_date, item.get("avanco_percentual")),
                "status": _status_template(item.get("status")),
                "statusLabel": _status_label(item.get("status")),
            }
        )

    schedule: list[dict[str, Any]] = []
    for group in group_order:
        rows = grouped.get(group)
        if rows:
            schedule.append({"group": group, "rows": rows})
    for group, rows in grouped.items():
        if group not in group_order and rows:
            schedule.append({"group": group, "rows": rows})
    return schedule

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




def _display_responsavel(value: Any) -> str:
    key = _norm_key(value)
    mapping = {
        "cateo": "CATEO",
        "cliente": "Cliente",
        "arquitetura": "Arquitetura",
        "tools": "TOOLS",
        "projetista": "Projetista",
        "fornecedor": "Fornecedor",
        "condominio": "Condomínio",
    }
    return mapping.get(key, _text(value, "Indefinido"))


def _split_responsaveis(value: Any) -> list[str]:
    raw = _text(value, "Indefinido")
    raw = re.sub(r"\s+", " ", raw.replace("\n", " ")).strip()
    if not raw:
        return ["Indefinido"]
    # Mantém barras como separador de corresponsáveis: CATEO / CLIENTE / ARQUITETURA.
    parts = [p.strip(" -•,;") for p in re.split(r"\s*/\s*", raw) if p.strip(" -•,;")]
    if not parts:
        parts = [raw]
    return [_display_responsavel(p) for p in parts]


def _is_item_aberto(status_norm: str) -> bool:
    return status_norm not in {"informativo", "concluido"}


def _is_prazo_critico_item(item: dict[str, Any], reference_date: Any = None) -> bool:
    status_norm = normalizar_status(item.get("status"))
    if not _is_item_aberto(status_norm):
        return False
    nivel = _nivel_template(item.get("criticidade"))
    if nivel in {"alto", "critico"}:
        return True
    incidencia = _number(item.get("incidencia") or item.get("sla"))
    if incidencia is not None and incidencia >= 2:
        return True
    prazo = _parse_date_any(item.get("prazo_vigente") or item.get("prazo") or item.get("termino") or item.get("prazo_limite"))
    ref = _parse_date_any(reference_date)
    if prazo and ref and prazo <= ref:
        return True
    return False


def _build_matriz_responsabilidades(dados: dict[str, Any], atividades: list[dict[str, Any]], reference_date: Any = None) -> list[dict[str, Any]]:
    """Aba 3: Matriz de responsabilidades.

    Consolida todos os itens por responsável. Quando o responsável vem composto
    por barras, cada parte recebe a contagem do item para evidenciar
    corresponsabilidade de Cliente, CATEO, Arquitetura, TOOLS etc.
    """
    matriz: dict[str, dict[str, Any]] = {}

    def ensure(resp: str) -> dict[str, Any]:
        if resp not in matriz:
            matriz[resp] = {
                "responsavel": resp,
                "acoesEmAberto": 0,
                "informacoes": 0,
                "concluidas": 0,
                "prazosCriticos": 0,
            }
        return matriz[resp]

    for item in atividades:
        if not isinstance(item, dict):
            continue
        status_norm = normalizar_status(item.get("status"))
        responsaveis = _split_responsaveis(_atividade_responsavel(item))
        for resp in responsaveis:
            row = ensure(resp)
            if status_norm == "informativo":
                row["informacoes"] += 1
            elif status_norm == "concluido":
                row["concluidas"] += 1
            else:
                row["acoesEmAberto"] += 1
                if _is_prazo_critico_item(item, reference_date):
                    row["prazosCriticos"] += 1

    ordem_preferencial = {"CATEO": 0, "Cliente": 1, "Arquitetura": 2, "TOOLS": 3}
    rows = list(matriz.values())
    rows.sort(
        key=lambda r: (
            ordem_preferencial.get(r["responsavel"], 99),
            -int(r["acoesEmAberto"]),
            -int(r["prazosCriticos"]),
            r["responsavel"],
        )
    )
    return rows



def _impact_reason(item: dict[str, Any], tipo: str) -> str:
    """Gera análise breve do motivo do impacto, evitando repetir a descrição da pendência."""
    titulo_norm = _norm_key(_atividade_titulo(item))
    texto = _norm_key(
        f"{_atividade_titulo(item)} {_atividade_descricao(item)} "
        f"{item.get('observacoes') or item.get('observacao') or item.get('historico_cronologico') or ''}"
    )
    prazo = _atividade_prazo(item)

    if tipo == "prazo":
        if "cronograma" in texto:
            return f"Afeta a programação das frentes e a previsibilidade das próximas liberações até {prazo}." if prazo != INFORMACAO_NAO_INFORMADA else "Afeta a programação das frentes e a previsibilidade das próximas liberações."
        if "demolicao" in texto:
            return "Pode condicionar a liberação e o sequenciamento dos serviços de demolição."
        if any(word in texto for word in ["mapa", "mao de obra", "instalacoes"]):
            return f"Impacta o planejamento de equipe/instalações e precisa ser consolidado até {prazo}." if prazo != INFORMACAO_NAO_INFORMADA else "Impacta o planejamento de equipe/instalações."
        if any(word in texto for word in ["retirada", "retirar", "moveis", "garagem"]):
            return "Pode restringir a liberação física da frente de demolição/execução."
        return f"Pendência aberta com potencial de interferir no prazo previsto até {prazo}." if prazo != INFORMACAO_NAO_INFORMADA else "Pendência aberta com potencial de interferir no prazo da obra."

    if tipo == "custo":
        if any(word in texto for word in ["orcamento", "custo"]):
            return "Depende de orçamento ou validação de custo para definição do caminho executivo."
        if any(word in texto for word in ["pagamento", "sinal"]):
            return "Depende de condição financeira/contratual para liberação junto a fornecedores."
        if any(word in texto for word in ["substituicao", "reforma", "cupins", "batentes"]):
            return "Pode alterar escopo e custo por necessidade de substituição ou reforma."
        if "fornecedor" in texto or "contratacao" in texto:
            return "Pode afetar contratação de fornecedores e composição de custos."
        return "Possui potencial de impacto financeiro ou necessidade de validação de escopo."

    if tipo == "projeto":
        if any(word in texto for word in ["arquitetura", "projeto", "projetista"]):
            return "Depende de definição técnica/projeto para liberar cotação, contratação ou execução."
        if any(word in texto for word in ["cliente", "aprovacao", "validacao", "definicao"]):
            return "Depende de aprovação ou definição do cliente para continuidade do item."
        if any(word in texto for word in ["caixilho", "caixilhos", "fachada"]):
            return "Depende de definição arquitetônica/cliente sobre intervenção na fachada."
        if any(word in texto for word in ["revestimento", "sacada", "terraco", "estanqueidade"]):
            return "Depende de validação técnica/cliente para confirmar solução da frente."
        return "Depende de definição técnica, cliente ou projetista para avanço seguro."

    if tipo == "documental":
        if "art" in texto or "arts" in texto:
            return "Exige ART/documentação vinculada à responsabilidade técnica da obra."
        if "contrato" in texto or "assinatura" in texto:
            return "Exige formalização contratual ou assinatura antes da liberação do serviço."
        if "pagamento" in texto or "sinal" in texto:
            return "Está condicionado à formalização documental antes de liberação financeira."
        if any(word in texto for word in ["responsavel tecnico", "alvara", "vinculacao"]):
            return "Relaciona-se à regularização documental e responsabilidade técnica."
        return "Requer controle documental/contratual para manter rastreabilidade e conformidade."

    return "Pendência classificada por potencial impacto gerencial."


def _impact_item_payload(item: dict[str, Any], idx: int, tipo: str = "") -> dict[str, Any]:
    prazo = _atividade_prazo(item)
    responsavel = _atividade_responsavel(item)
    return {
        "id": _text(item.get("id") or item.get("id_item"), f"{idx:02d}"),
        "title": _atividade_titulo(item),
        "desc": _impact_reason(item, tipo),
        "responsible": responsavel,
        "deadline": prazo,
        "status": _status_label(item.get("status")),
        "level": _level_label(item.get("criticidade") or item.get("prioridade") or item.get("level")),
    }


def _impact_types_for_item(item: dict[str, Any]) -> list[str]:
    """Classifica pendências por impacto gerencial usando texto da ata."""
    titulo = _atividade_titulo(item)
    descricao = _atividade_descricao(item)
    observacao = _text(item.get("observacoes") or item.get("observacao") or item.get("historico_cronologico"))
    texto = _norm_key(f"{titulo} {descricao} {observacao}")
    tipos: list[str] = []

    if any(word in texto for word in [
        "cronograma", "demolicao", "liberacao", "liberar", "execucao", "executar", "mapa",
        "mao de obra", "instalacoes", "hidraulicas", "obra", "atraso", "entrega", "enviar",
        "retirada", "retirar", "moveis", "garagem", "estanqueidade",
    ]):
        tipos.append("prazo")

    if any(word in texto for word in [
        "orcamento", "custo", "pagamento", "sinal", "substituicao", "substituir", "reforma",
        "escopo", "fornecedor", "fornecedores", "cupins", "batentes", "contratacao",
    ]):
        tipos.append("custo")

    if any(word in texto for word in [
        "arquitetura", "projetista", "projeto", "cliente", "definicao", "definicoes", "validacao",
        "validar", "aprovacao", "aprovado", "aprovou", "caixilho", "caixilhos", "revestimento",
        "detalhamento", "fachada", "tijolinho", "terraco", "sacada",
    ]):
        tipos.append("projeto")

    if any(word in texto for word in [
        "contrato", "contratos", "art", "arts", "assinatura", "assinar", "alvara", "responsavel tecnico",
        "documento", "documental", "vinculacao", "vinculada", "vinculadas", "testemunhas", "contratante",
        "contratada", "interveniente",
    ]):
        tipos.append("documental")

    return tipos or ["prazo"]


def _build_impactos_pendencias(atividades: list[dict[str, Any]], pendencias: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aba 04: agrupa todas as pendências por tipo de impacto.

    Usa todos os itens não concluídos da ata, inclusive informativos relevantes,
    e não apenas os itens da ata atual.
    """
    base_items = [item for item in atividades if isinstance(item, dict) and normalizar_status(item.get("status")) != "concluido"]
    if not base_items:
        base_items = [item for item in pendencias if isinstance(item, dict) and normalizar_status(item.get("status")) != "concluido"]

    groups: dict[str, dict[str, Any]] = {
        "prazo": {
            "id": "prazo",
            "title": "Impacto em prazo",
            "description": "Itens que podem atrasar contratação, demolição, liberação de projeto ou execução.",
            "items": [],
        },
        "custo": {
            "id": "custo",
            "title": "Impacto em custo",
            "description": "Itens que dependem de orçamento, aprovação financeira, substituição ou definição de escopo.",
            "items": [],
        },
        "projeto": {
            "id": "projeto",
            "title": "Impacto em projeto/definição",
            "description": "Itens que dependem de arquitetura, cliente, projetistas ou validações técnicas.",
            "items": [],
        },
        "documental": {
            "id": "documental",
            "title": "Impacto documental/contratual",
            "description": "Contratos, ARTs, assinaturas, vínculo de responsabilidade técnica e documentos formais.",
            "items": [],
        },
    }

    seen_by_group: dict[str, set[str]] = {key: set() for key in groups}
    for idx, item in enumerate(base_items, start=1):
        item_key = _atividade_key(item)
        for tipo in _impact_types_for_item(item):
            if item_key in seen_by_group[tipo]:
                continue
            seen_by_group[tipo].add(item_key)
            groups[tipo]["items"].append(_impact_item_payload(item, idx, tipo))

    return [groups[key] for key in ["prazo", "custo", "projeto", "documental"]]

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
        desc = _compact_text(item.get("descricao") or item.get("desc") or _atividade_descricao(item), 700)
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
                "body": _compact_text(item.get("descricao") or item.get("resultado_esperado") or item.get("body"), 600),
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
                "body": _compact_text(item.get("action") or item.get("desc") or item.get("descricao"), 600) or "Acompanhar evolução na próxima reunião.",
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
    for key in ["criticalPoints", "phases", "schedule", "ambientes", "matrizResponsabilidades", "impactosPendencias", "extraEscopo", "pendenciasTools", "planoAcao", "ata", "deliberacoes", "historicoMudancas"]:
        incoming = gpt3.get(key)
        if not isinstance(incoming, list):
            continue
        # Evita card vazio, principalmente em extraEscopo.
        incoming = [
            item for item in incoming
            if not isinstance(item, dict)
            or _text(item.get("title") or item.get("titulo") or item.get("body") or item.get("descricao") or item.get("text") or item.get("description"))
        ]
        if not merged.get(key) and incoming:
            merged[key] = incoming

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
        "phases": _build_phases(dados, atividades, current_ata=relatorio.numero_ata),
        "schedule": _build_schedule(dados, atividades, current_ata=relatorio.numero_ata, reference_date=relatorio.data_referencia),
        "ambientes": _build_ambientes(dados, atividades),
        "matrizResponsabilidades": _build_matriz_responsabilidades(dados, atividades, relatorio.data_referencia),
        "impactosPendencias": _build_impactos_pendencias(atividades, pendencias),
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
