from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime
from typing import Any


CRITICIDADE_MAP = {
    "critica": "critico",
    "critico": "critico",
    "crítica": "critico",
    "crítico": "critico",
    "alta": "alto",
    "alto": "alto",
    "media": "moderado",
    "média": "moderado",
    "medio": "moderado",
    "médio": "moderado",
    "moderada": "moderado",
    "moderado": "moderado",
    "baixa": "baixo",
    "baixo": "baixo",
}

STATUS_MAP = {
    "concluido": "concluido",
    "concluído": "concluido",
    "em andamento": "andamento",
    "andamento": "andamento",
    "pendente": "pendente",
    "atrasada": "bloqueante",
    "atrasado": "bloqueante",
    "bloqueante": "bloqueante",
    "bloqueado": "bloqueante",
    "não iniciado": "nao_iniciado",
    "nao iniciado": "nao_iniciado",
    "informativo": "informativo",
}


def remover_acentos(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor or "")
    return "".join(ch for ch in texto if not unicodedata.combining(ch))


def safe_text(valor: Any, default: str = "") -> str:
    if valor is None:
        return default
    texto = str(valor).strip()
    return texto if texto else default


def slugify_nome_obra(nome: str) -> str:
    texto = remover_acentos(nome).upper()
    texto = re.sub(r"[^A-Z0-9]+", "_", texto)
    texto = re.sub(r"_+", "_", texto).strip("_")
    return texto or "OBRA"


def normalizar_chave(valor: str | None) -> str:
    texto = remover_acentos(valor or "").lower().strip()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_criticidade(valor: Any) -> str | None:
    if valor is None:
        return None
    chave = normalizar_chave(str(valor))
    if "crit" in chave:
        return "critico"
    if "alta" in chave or chave == "alto":
        return "alto"
    if "media" in chave or "moder" in chave or chave == "medio":
        return "moderado"
    if "baixa" in chave or chave == "baixo":
        return "baixo"
    return CRITICIDADE_MAP.get(chave, chave or None)


def normalizar_status(valor: Any) -> str | None:
    if valor is None:
        return None
    chave = normalizar_chave(str(valor))
    if "concl" in chave or "resolvido" in chave:
        return "concluido"
    if "bloq" in chave or "atras" in chave:
        return "bloqueante"
    if "andamento" in chave or "execucao" in chave or "execução" in str(valor).lower():
        return "andamento"
    if "pend" in chave or "aberto" in chave:
        return "pendente"
    if "nao iniciado" in chave or "não iniciado" in str(valor).lower():
        return "nao_iniciado"
    if "inform" in chave:
        return "informativo"
    return STATUS_MAP.get(chave, chave or None)


def safe_date(valor: Any) -> date | None:
    if valor in (None, "", "Não informado", "INFORMAÇÃO INSUFICIENTE", "INFORMAÇÃO ILEGÍVEL"):
        return None
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if isinstance(valor, datetime):
        return valor.date()

    texto = str(valor).strip()
    if not texto:
        return None

    formatos = ["%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y"]
    for fmt in formatos:
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            pass

    match = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", texto)
    if match:
        dia, mes, ano = match.groups()
        ano_int = int(ano) if ano else datetime.now().year
        if ano_int < 100:
            ano_int += 2000
        try:
            return date(ano_int, int(mes), int(dia))
        except ValueError:
            return None

    return None


def gerar_hash_item(obra_id: int, titulo: str, responsavel: str | None = None) -> str:
    base = "|".join([
        str(obra_id),
        normalizar_chave(titulo),
        normalizar_chave(responsavel or ""),
    ])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def gerar_nome_output(
    nome_obra: str,
    numero_ata: str | None,
    data_referencia: date | str | None,
    etapa_numero: int,
    etapa_nome: str,
) -> str:
    slug = slugify_nome_obra(nome_obra)
    ata = re.sub(r"[^0-9A-Za-z]+", "", numero_ata or "SEMATA").upper()
    if ata and not ata.upper().startswith("ATA"):
        ata = f"ATA{ata}"
    if isinstance(data_referencia, date):
        data_txt = data_referencia.isoformat()
    else:
        data_txt = safe_text(data_referencia, "SEM_DATA")
    etapa_slug = slugify_nome_obra(etapa_nome)
    return f"{slug}_{ata}_{data_txt}_STEP{etapa_numero:02d}_{etapa_slug}"


def compact_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: compact_json(v) for k, v in value.items() if v not in (None, "", [], {})}
    if isinstance(value, list):
        return [compact_json(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
