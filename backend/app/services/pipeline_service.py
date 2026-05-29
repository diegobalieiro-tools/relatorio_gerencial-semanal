from __future__ import annotations

import asyncio
import copy
import json
import re
import unicodedata
from datetime import date
from typing import Any

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.obra import Obra
from app.models.relatorio import RelatorioEtapa, RelatorioSemanal
from app.services.dictionary_service import load_dictionaries_context
from app.services.history_service import build_resumo_historico_normalizado
from app.services.normalization_service import gerar_nome_output, safe_date
from app.services.openai_service import OpenAIJsonResult, OpenAIService
from app.services.persistence_service import persist_output_gpt2
from app.services.render_service import render_report_html
from app.services.report_adapter_service import build_report_json_from_gpt2
from app.services.storage_service import StoredFileContext, build_files_context_text, save_uploads

PROMPT_1 = "prompt_01_leitura_visual_ocr_validacao.txt"
PROMPT_2 = "prompt_02_estruturacao_historico_analise.txt"
PROMPT_3 = "prompt_03_report_json_final.txt"

ETAPA_UPLOAD = "upload_recebido"
ETAPA_1 = "leitura_visual_ocr_validacao"
ETAPA_2 = "estruturacao_historico_analise"
ETAPA_PERSISTENCIA = "persistencia_dados_historicos"
ETAPA_3 = "report_json_final"
ETAPA_RENDER = "renderizacao_html"
ETAPA_CONCLUIDO = "concluido"

# Os números abaixo controlam a ordem visual no componente PipelineStatus.
# Não representam número do prompt; são apenas posição operacional.
PIPELINE_STEPS: list[tuple[int, str]] = [
    (0, ETAPA_UPLOAD),
    (10, ETAPA_1),
    (20, ETAPA_2),
    (30, ETAPA_PERSISTENCIA),
    (40, ETAPA_3),
    (50, ETAPA_RENDER),
    (60, ETAPA_CONCLUIDO),
]


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _get_obra(db: Session, obra_id: int) -> Obra:
    obra = db.get(Obra, obra_id)
    if not obra:
        raise ValueError("Obra não encontrada.")
    return obra


def _upsert_etapa(
    db: Session,
    relatorio: RelatorioSemanal,
    etapa_numero: int,
    etapa_nome: str,
    status: str,
    input_json: dict[str, Any] | None = None,
    output_json: dict[str, Any] | None = None,
    erro: str | None = None,
    result: OpenAIJsonResult | None = None,
) -> RelatorioEtapa:
    etapa = (
        db.query(RelatorioEtapa)
        .filter(RelatorioEtapa.relatorio_id == relatorio.id, RelatorioEtapa.etapa_numero == etapa_numero)
        .first()
    )

    if not etapa:
        etapa = RelatorioEtapa(
            relatorio_id=relatorio.id,
            obra_id=relatorio.obra_id,
            etapa_numero=etapa_numero,
            etapa_nome=etapa_nome,
        )

    etapa.status = status
    etapa.input_json = input_json if input_json is not None else etapa.input_json
    etapa.output_json = output_json if output_json is not None else etapa.output_json
    etapa.erro = erro
    etapa.prompt_version = "v1"
    etapa.nome_output = gerar_nome_output(
        relatorio.obra.nome if relatorio.obra else "OBRA",
        relatorio.numero_ata,
        relatorio.data_referencia,
        etapa_numero,
        etapa_nome,
    )

    if result:
        etapa.modelo_usado = result.model_used
        etapa.tokens_entrada = result.tokens_input
        etapa.tokens_saida = result.tokens_output

    db.add(etapa)
    db.flush()
    return etapa


def _etapas_response(db: Session, relatorio_id: int) -> list[dict[str, Any]]:
    etapas = (
        db.query(RelatorioEtapa)
        .filter(RelatorioEtapa.relatorio_id == relatorio_id)
        .order_by(RelatorioEtapa.etapa_numero.asc())
        .all()
    )
    return [
        {
            "etapa_numero": etapa.etapa_numero,
            "etapa_nome": etapa.etapa_nome,
            "status": etapa.status,
            "erro": etapa.erro,
        }
        for etapa in etapas
    ]




_REPROCESS_SECTION_ALIASES: dict[str, str] = {
    "plano": "plano",
    "plano de acao": "plano",
    "plano de ação": "plano",
    "acao": "plano",
    "ação": "plano",
    "impactos": "extra",
    "impacto": "extra",
    "extra escopo": "extra",
    "extra-escopo": "extra",
    "matriz": "ambientes",
    "matriz de responsabilidades": "ambientes",
    "cronograma": "cronograma",
    "cronograma da ata": "cronograma",
    "ata": "ata",
    "deliberacoes": "deliberacoes",
    "deliberações": "deliberacoes",
    "pendencias": "criticos",
    "pendências": "criticos",
}


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_date_br(value: str) -> str:
    value = str(value or "").strip()
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", value)
    if not match:
        return value
    day, month, year = match.groups()
    if len(year) == 2:
        year = "20" + year
    return f"{int(day):02d}/{int(month):02d}/{year}"


def _strings_match_item(container: dict[str, Any], target_norm: str) -> bool:
    if not target_norm:
        return False
    candidate_values = [
        container.get("title"),
        container.get("titulo"),
        container.get("item"),
        container.get("name"),
        container.get("text"),
        container.get("descricao"),
        container.get("description"),
    ]
    for value in candidate_values:
        normalized = _normalize_text(value)
        if normalized and (target_norm in normalized or normalized in target_norm):
            return True
    return False


def _replace_date_in_value(value: Any, old_date: str, new_date: str) -> Any:
    if not isinstance(value, str):
        return value
    variants = {old_date, old_date.replace("/20", "/"), old_date.lstrip("0")}
    updated = value
    for variant in variants:
        updated = updated.replace(variant, new_date)
    return updated


def _update_matching_item_dates(value: Any, target_norm: str, old_date: str, new_date: str) -> bool:
    """Atualiza prazo/término dentro de qualquer estrutura que represente o item."""
    changed = False
    if isinstance(value, list):
        for item in value:
            changed = _update_matching_item_dates(item, target_norm, old_date, new_date) or changed
        return changed

    if not isinstance(value, dict):
        return False

    is_match = _strings_match_item(value, target_norm)
    if is_match:
        for key in ["end", "deadline", "prazo", "prazo_limite", "prazoLimite", "fim", "termino", "término"]:
            if key in value:
                value[key] = new_date
                changed = True
        for key, item_value in list(value.items()):
            if isinstance(item_value, str):
                replaced = _replace_date_in_value(item_value, old_date, new_date)
                if replaced != item_value:
                    value[key] = replaced
                    changed = True
            elif isinstance(item_value, list):
                new_list = []
                list_changed = False
                for element in item_value:
                    replaced = _replace_date_in_value(element, old_date, new_date)
                    if replaced != element:
                        list_changed = True
                    new_list.append(replaced)
                if list_changed:
                    value[key] = new_list
                    changed = True

    for child in value.values():
        if isinstance(child, (dict, list)):
            changed = _update_matching_item_dates(child, target_norm, old_date, new_date) or changed
    return changed


def _hide_requested_sections(report_json: dict[str, Any], instructions_norm: str) -> bool:
    changed = False
    hidden = set(report_json.get("hiddenSections") or report_json.get("hidden_sections") or [])
    for alias, section_id in _REPROCESS_SECTION_ALIASES.items():
        patterns = [
            f"remova a aba {alias}",
            f"remover a aba {alias}",
            f"retire a aba {alias}",
            f"oculte a aba {alias}",
            f"remova o {alias}",
            f"remover o {alias}",
        ]
        if any(pattern in instructions_norm for pattern in patterns):
            hidden.add(section_id)
            changed = True
            if section_id == "plano":
                report_json["planoAcao"] = []
            elif section_id == "extra":
                report_json["impactosPendencias"] = []
                report_json["extraEscopo"] = []
    if changed:
        report_json["hiddenSections"] = sorted(hidden)
    return changed


def _normalize_responsavel_label(value: str) -> str:
    norm = _normalize_text(value)
    mapping = {
        "cliente": "CLIENTE",
        "clientes": "CLIENTE",
        "cateo": "CATEO",
        "construtora": "CATEO",
        "arquitetura": "ARQUITETURA",
        "arquiteto": "ARQUITETURA",
        "projetista": "PROJETISTA",
        "projetistas": "PROJETISTA",
        "tools": "TOOLS",
        "gerenciadora": "TOOLS",
    }
    return mapping.get(norm, str(value or "").strip().upper())


def _extract_responsavel_instruction(instructions: str, new_date: str | None = None) -> tuple[str | None, str | None]:
    """Extrai instruções simples do tipo: 'é responsabilidade do cliente aprovar'."""
    pattern = re.compile(
        r"responsabilidade\s+d[aoe]\s+(?P<resp>[A-Za-zÀ-ÿ/ ]+?)(?:\s+(?P<verb>aprovar|validar|enviar|executar|definir|retirar|liberar|assinar|acompanhar))?(?:[.;,]|$)",
        flags=re.IGNORECASE,
    )
    match = pattern.search(instructions or "")
    if not match:
        return None, None

    resp_raw = (match.group("resp") or "").strip()
    verb = (match.group("verb") or "acompanhar").strip().lower()
    resp = _normalize_responsavel_label(resp_raw)

    verb_map = {
        "aprovar": "aprovar",
        "validar": "validar",
        "enviar": "enviar",
        "executar": "executar",
        "definir": "definir",
        "retirar": "retirar",
        "liberar": "liberar",
        "assinar": "assinar",
        "acompanhar": "acompanhar",
    }
    verb_txt = verb_map.get(verb, verb)
    action = f"{resp.title()} deve {verb_txt}"
    if new_date:
        action += f" até {new_date}"
    action += "."
    return resp, action


def _replace_any_date_in_text(value: str, new_date: str) -> str:
    return re.sub(r"\d{1,2}/\d{1,2}/\d{2,4}", new_date, value, count=1)


def _update_matching_item_fields(
    value: Any,
    target_norm: str,
    new_date: str | None = None,
    new_responsavel: str | None = None,
    action_text: str | None = None,
) -> bool:
    """Atualiza prazo/responsável/ação de um item em qualquer seção do report_json."""
    changed = False

    if isinstance(value, list):
        for item in value:
            changed = _update_matching_item_fields(item, target_norm, new_date, new_responsavel, action_text) or changed
        return changed

    if not isinstance(value, dict):
        return False

    is_match = _strings_match_item(value, target_norm)
    if is_match:
        if new_date:
            for key in ["end", "deadline", "prazo", "prazo_limite", "prazoLimite", "fim", "termino", "término", "meta"]:
                if key in value:
                    if isinstance(value[key], str) and key == "meta":
                        if re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", value[key]):
                            value[key] = _replace_any_date_in_text(value[key], new_date)
                        else:
                            value[key] = f"{value[key]} · {new_date}"
                    else:
                        value[key] = new_date
                    changed = True
            for key, item_value in list(value.items()):
                if isinstance(item_value, str):
                    replaced = _replace_any_date_in_text(item_value, new_date) if re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", item_value) else item_value
                    if replaced != item_value:
                        value[key] = replaced
                        changed = True
                elif isinstance(item_value, list):
                    new_list = []
                    list_changed = False
                    for element in item_value:
                        if isinstance(element, str):
                            if re.search(r"prazo\s*:", element, flags=re.IGNORECASE):
                                replaced = re.sub(r"Prazo\s*:\s*[^,;|]+", f"Prazo: {new_date}", element, flags=re.IGNORECASE)
                            else:
                                replaced = _replace_any_date_in_text(element, new_date) if re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", element) else element
                            if replaced != element:
                                list_changed = True
                            new_list.append(replaced)
                        else:
                            new_list.append(element)
                    if list_changed:
                        value[key] = new_list
                        changed = True

        if new_responsavel:
            for key in ["resp", "responsible", "responsavel", "responsável", "responsavel_pendencia"]:
                if key in value:
                    value[key] = new_responsavel
                    changed = True
            if isinstance(value.get("meta"), str):
                parts = [part.strip() for part in value["meta"].split("·")]
                if parts:
                    parts[0] = new_responsavel
                    value["meta"] = " · ".join(parts)
                    changed = True
            if isinstance(value.get("tags"), list):
                tags = []
                for tag in value["tags"]:
                    if isinstance(tag, str) and _normalize_text(tag).startswith("responsavel"):
                        tags.append(f"Responsável: {new_responsavel}")
                        changed = True
                    else:
                        tags.append(tag)
                value["tags"] = tags

        if action_text:
            for key in ["action", "actionDescription", "acao", "ação", "decision"]:
                if key in value:
                    value[key] = action_text
                    changed = True

    for child in value.values():
        if isinstance(child, (dict, list)):
            changed = _update_matching_item_fields(child, target_norm, new_date, new_responsavel, action_text) or changed
    return changed


def _extract_prazo_sem_data_antiga(instructions: str) -> list[tuple[str, str]]:
    """Captura frases como: 'Cronograma de contratações agora tem o prazo até o dia 01/06/2026'."""
    patterns = [
        re.compile(
            r"(?P<title>[A-Za-zÀ-ÿ0-9 /ºª_.-]{3,}?)\s+(?:agora\s+)?(?:tem|passa\s+a\s+ter|ficou\s+com)\s+(?:o\s+)?prazo\s+(?:ate|até|para)\s+(?:o\s+dia\s+)?(?P<new>\d{1,2}/\d{1,2}/\d{2,4})",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"prazo\s+d[eoa]\s+(?P<title>[A-Za-zÀ-ÿ0-9 /ºª_.-]{3,}?)\s+(?:ate|até|para)\s+(?:o\s+dia\s+)?(?P<new>\d{1,2}/\d{1,2}/\d{2,4})",
            flags=re.IGNORECASE,
        ),
    ]
    matches: list[tuple[str, str]] = []
    for pattern in patterns:
        for match in pattern.finditer(instructions or ""):
            title = match.group("title").strip(" .,:;\n\t")
            if title:
                matches.append((title, _normalize_date_br(match.group("new"))))
    return matches


def _apply_reprocess_instructions_locally(report_json: dict[str, Any], instructions: str) -> tuple[dict[str, Any], bool, list[str]]:
    """Aplica ajustes simples sem chamar IA, evitando reprocessamentos travados.

    Cobre os pedidos operacionais mais comuns da tela: remover/ocultar abas e
    corrigir prazo/término de um item específico. Quando não reconhecer nada,
    o fluxo ainda pode recorrer à IA como fallback.
    """
    updated = copy.deepcopy(report_json)
    instructions_norm = _normalize_text(instructions)
    changed = False
    notes: list[str] = []

    if _hide_requested_sections(updated, instructions_norm):
        changed = True
        notes.append("Abas solicitadas foram ocultadas no relatório.")

    prazo_pattern = re.compile(
        r"prazo\s+d[eoa]\s+(?P<title>.+?)\s+alterad[oa]\s+de\s+(?P<old>\d{1,2}/\d{1,2}/\d{2,4})\s+para\s+(?P<new>\d{1,2}/\d{1,2}/\d{2,4})",
        flags=re.IGNORECASE,
    )
    matched_titles: set[str] = set()
    for match in prazo_pattern.finditer(instructions):
        title = match.group("title").strip(" .,:;\n\t")
        old_date = _normalize_date_br(match.group("old"))
        new_date = _normalize_date_br(match.group("new"))
        target_norm = _normalize_text(title)
        new_resp, action_text = _extract_responsavel_instruction(instructions, new_date)
        if _update_matching_item_dates(updated, target_norm, old_date, new_date):
            _update_matching_item_fields(updated, target_norm, new_responsavel=new_resp, action_text=action_text)
            changed = True
            matched_titles.add(target_norm)
            notes.append(f"Prazo de '{title}' atualizado de {old_date} para {new_date}.")

    for title, new_date in _extract_prazo_sem_data_antiga(instructions):
        target_norm = _normalize_text(title)
        if target_norm in matched_titles:
            continue
        new_resp, action_text = _extract_responsavel_instruction(instructions, new_date)
        if _update_matching_item_fields(updated, target_norm, new_date=new_date, new_responsavel=new_resp, action_text=action_text):
            changed = True
            matched_titles.add(target_norm)
            msg = f"Prazo de '{title}' atualizado para {new_date}."
            if new_resp:
                msg += f" Responsável ajustado para {new_resp}."
            notes.append(msg)

    if notes:
        quality = updated.setdefault("quality", {})
        warnings = quality.setdefault("warnings", [])
        if isinstance(warnings, list):
            warnings.extend({"tipo": "reprocessamento", "descricao": note} for note in notes)

    return updated, changed, notes


class PipelineService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.openai = OpenAIService()

    async def iniciar_processamento(
        self,
        obra_id: int,
        numero_ata: str | None,
        data_referencia: date,
        arquivos: list[UploadFile] | None = None,
    ) -> tuple[RelatorioSemanal, list[StoredFileContext]]:
        """Cria o relatório, salva uploads e inicializa etapas.

        Esta etapa é propositalmente curta para a API responder rápido ao frontend.
        O processamento pesado de GPT/renderização roda em background, permitindo que
        a tela consulte `/api/pipeline/{id}/status` e mostre cada etapa em tempo real.
        """
        obra = _get_obra(self.db, obra_id)

        relatorio = RelatorioSemanal(
            obra_id=obra.id,
            numero_ata=numero_ata,
            data_referencia=data_referencia,
            titulo="Relatório Semanal de Obra",
            status="processando",
            template_version="template-aplicacao-v1",
        )
        self.db.add(relatorio)
        self.db.commit()
        self.db.refresh(relatorio)
        relatorio.obra = obra

        stored_files = await save_uploads(self.db, relatorio.id, arquivos or [])
        _upsert_etapa(
            self.db,
            relatorio,
            0,
            ETAPA_UPLOAD,
            "concluido",
            output_json={"quantidade_arquivos": len(stored_files)},
        )
        for etapa_numero, etapa_nome in PIPELINE_STEPS[1:]:
            _upsert_etapa(self.db, relatorio, etapa_numero, etapa_nome, "pendente")

        self.db.commit()
        self.db.refresh(relatorio)
        return relatorio, stored_files

    async def continuar_processamento(
        self,
        relatorio_id: int,
        stored_files: list[StoredFileContext],
        conteudo_whatsapp: str | None = None,
        conteudo_transcricao: str | None = None,
        semana_referencia: str | None = None,
        observacoes: str | None = None,
    ) -> None:
        relatorio = self.db.get(RelatorioSemanal, relatorio_id)
        if not relatorio:
            raise ValueError("Relatório não encontrado para processamento em background.")

        obra = _get_obra(self.db, relatorio.obra_id)
        relatorio.obra = obra
        current_step: tuple[int, str] | None = None

        try:
            dictionaries = load_dictionaries_context()
            files_context_text = build_files_context_text(stored_files)
            history = build_resumo_historico_normalizado(self.db, obra.id)

            base_context = {
                "nome_obra": obra.nome,
                "cliente": obra.cliente,
                "gerenciadora": obra.gerenciadora,
                "empresa_executora": obra.executora,
                "engenheiro_responsavel": obra.engenheiro_responsavel or "",
                "projetistas": (obra.dicionario_tecnico_json or {}).get("projetistas", []),
                "fornecedores": (obra.dicionario_tecnico_json or {}).get("fornecedores", []),
                "ano_vigente": obra.ano_vigente or relatorio.data_referencia.year,
                "data_reuniao_atual": relatorio.data_referencia.isoformat(),
                "numero_ata": relatorio.numero_ata or "",
                "prazo_contratual": obra.prazo_contratual.isoformat() if obra.prazo_contratual else "",
                "conteudo_whatsapp": conteudo_whatsapp or "",
                "conteudo_transcricao": conteudo_transcricao or "",
                "semana_referencia": semana_referencia or "",
                "observacoes": observacoes or "",
                **dictionaries,
            }

            current_step = (10, ETAPA_1)
            step1_input = {
                **base_context,
                "arquivos_contexto_extraido": files_context_text,
            }
            _upsert_etapa(self.db, relatorio, *current_step, "processando", input_json=step1_input)
            self.db.commit()

            step1 = await self.openai.run_prompt_json(PROMPT_1, step1_input, files=stored_files)
            _upsert_etapa(
                self.db,
                relatorio,
                *current_step,
                "concluido",
                input_json=step1_input,
                output_json=step1.data,
                result=step1,
            )
            self.db.commit()

            current_step = (20, ETAPA_2)
            step2_input = {
                **base_context,
                "historico_anterior": _json_dump(history.get("ultimo_report_json_resumido", {})),
                "resumo_historico_normalizado": _json_dump(history),
                "extracao_validada": _json_dump(step1.data),
            }
            _upsert_etapa(self.db, relatorio, *current_step, "processando", input_json=step2_input)
            self.db.commit()

            step2 = await self.openai.run_prompt_json(PROMPT_2, step2_input)
            _upsert_etapa(
                self.db,
                relatorio,
                *current_step,
                "concluido",
                input_json=step2_input,
                output_json=step2.data,
                result=step2,
            )
            self.db.commit()

            current_step = (30, ETAPA_PERSISTENCIA)
            _upsert_etapa(
                self.db,
                relatorio,
                *current_step,
                "processando",
                input_json={"fonte": "output_gpt2"},
            )
            self.db.commit()
            persist_result = persist_output_gpt2(self.db, obra.id, relatorio.id, step2.data)
            _upsert_etapa(
                self.db,
                relatorio,
                *current_step,
                "concluido",
                input_json={"fonte": "output_gpt2"},
                output_json=persist_result.as_dict(),
            )
            self.db.commit()

            current_step = (40, ETAPA_3)
            step3_input = {
                "dados_estruturados_analise": _json_dump(step2.data),
            }
            _upsert_etapa(self.db, relatorio, *current_step, "processando", input_json=step3_input)
            self.db.commit()

            step3 = await self.openai.run_prompt_json(PROMPT_3, step3_input)

            dados_gpt1_enriquecido = {
                **(step1.data or {}),
                "arquivos_contexto_extraido": files_context_text,
            }

            final_report_json = build_report_json_from_gpt2(
                obra=obra,
                relatorio=relatorio,
                dados_gpt2=step2.data,
                dados_gpt3=step3.data,
                dados_gpt1=dados_gpt1_enriquecido,
            )

            _upsert_etapa(
                self.db,
                relatorio,
                *current_step,
                "concluido",
                input_json=step3_input,
                output_json={"raw_gpt3": step3.data, "report_json_final": final_report_json},
                result=step3,
            )
            self.db.commit()

            current_step = (50, ETAPA_RENDER)
            _upsert_etapa(
                self.db,
                relatorio,
                *current_step,
                "processando",
                input_json={"report_json": "relatorios_semanais.report_json"},
            )
            self.db.commit()

            relatorio.report_json = final_report_json
            html_path = render_report_html(relatorio.id, final_report_json)
            relatorio.html_path = html_path
            relatorio.status = "concluido"
            self.db.add(relatorio)
            _upsert_etapa(
                self.db,
                relatorio,
                *current_step,
                "concluido",
                input_json={"report_json": "relatorios_semanais.report_json"},
                output_json={"html_path": html_path},
            )
            current_step = (60, ETAPA_CONCLUIDO)
            _upsert_etapa(
                self.db,
                relatorio,
                *current_step,
                "concluido",
                output_json={"mensagem": "Pipeline concluída com sucesso."},
            )
            self.db.commit()

        except Exception as exc:  # noqa: BLE001
            relatorio.status = "erro"
            self.db.add(relatorio)
            if current_step:
                _upsert_etapa(
                    self.db,
                    relatorio,
                    current_step[0],
                    current_step[1],
                    "erro",
                    erro=str(exc),
                )
            _upsert_etapa(
                self.db,
                relatorio,
                99,
                "erro_pipeline",
                "erro",
                input_json={"relatorio_id": relatorio_id},
                erro=str(exc),
            )
            self.db.commit()
            raise


    def iniciar_reprocessamento(
        self,
        relatorio_id: int,
        instrucoes: str,
    ) -> dict[str, Any]:
        """Inicializa o reprocessamento e retorna rápido para o frontend acompanhar."""
        relatorio = self.db.get(RelatorioSemanal, relatorio_id)
        if not relatorio:
            raise ValueError("Relatório não encontrado.")

        instrucoes_limpas = (instrucoes or "").strip()
        if not instrucoes_limpas:
            raise ValueError("Informe as mudanças desejadas antes de reprocessar.")

        if not relatorio.report_json:
            raise ValueError("Relatório ainda não possui report_json para reprocessamento.")

        if str(relatorio.status or "").lower() == "reprocessando":
            raise RuntimeError("Já existe um reprocessamento em andamento para este relatório. Aguarde a conclusão antes de iniciar outro.")

        # Limpa erro de tentativa anterior para a tela não continuar mostrando falha antiga.
        (
            self.db.query(RelatorioEtapa)
            .filter(RelatorioEtapa.relatorio_id == relatorio.id, RelatorioEtapa.etapa_numero == 99)
            .delete(synchronize_session=False)
        )

        relatorio.status = "reprocessando"
        self.db.add(relatorio)
        _upsert_etapa(
            self.db,
            relatorio,
            70,
            "reprocessamento_com_instrucoes",
            "processando",
            input_json={"instrucoes": instrucoes_limpas},
        )
        _upsert_etapa(
            self.db,
            relatorio,
            80,
            "renderizacao_html_reprocessamento",
            "pendente",
        )
        _upsert_etapa(
            self.db,
            relatorio,
            90,
            "reprocessamento_concluido",
            "pendente",
        )
        self.db.commit()

        return {
            "relatorio_id": relatorio.id,
            "status": relatorio.status,
            "mensagem": "Reprocessamento iniciado. Acompanhe o progresso na tela.",
            "etapas": _etapas_response(self.db, relatorio.id),
        }

    async def reprocessar_com_instrucoes(
        self,
        relatorio_id: int,
        instrucoes: str,
    ) -> dict[str, Any]:
        """Reprocessa o JSON/HTML final usando instruções textuais do usuário.

        Este fluxo não relê anexos nem refaz GPT 1/GPT 2. Ele parte do
        `report_json` já validado e aplica ajustes pontuais solicitados na tela
        do relatório, como remover uma seção, reforçar um item ou acrescentar
        uma informação complementar escrita pelo usuário.
        """
        relatorio = self.db.get(RelatorioSemanal, relatorio_id)
        if not relatorio:
            raise ValueError("Relatório não encontrado.")

        instrucoes_limpas = (instrucoes or "").strip()
        if not instrucoes_limpas:
            raise ValueError("Informe as mudanças desejadas antes de reprocessar.")

        if not relatorio.report_json:
            raise ValueError("Relatório ainda não possui report_json para reprocessamento.")

        current_step: tuple[int, str] | None = (70, "reprocessamento_com_instrucoes")

        try:
            relatorio.status = "reprocessando"
            self.db.add(relatorio)
            _upsert_etapa(
                self.db,
                relatorio,
                *current_step,
                "processando",
                input_json={"instrucoes": instrucoes_limpas},
            )
            self.db.commit()

            report_json_atual = relatorio.report_json
            novo_report_json, local_changed, local_notes = _apply_reprocess_instructions_locally(
                report_json_atual,
                instrucoes_limpas,
            )

            if not local_changed:
                prompt = f"""
Você é um agente de revisão controlada de relatório executivo de obra.

Sua tarefa é aplicar as INSTRUÇÕES DO USUÁRIO ao REPORT_JSON ATUAL e devolver um novo JSON completo, mantendo exatamente a mesma estrutura de chaves já existente.

REGRAS OBRIGATÓRIAS:
1. Retorne apenas JSON válido.
2. Preserve todas as chaves, arrays e estruturas existentes sempre que possível.
3. Não invente fatos, datas, responsáveis, valores ou decisões.
4. Só altere o que o usuário pediu explicitamente.
5. Se o usuário pedir para remover uma seção/item, remova apenas esse trecho.
6. Se o usuário fornecer informação complementar, insira como complemento textual, sem mudar evidências já existentes.
7. Não altere visual/design; isso é responsabilidade do template HTML.
8. Não apague dados técnicos úteis sem pedido explícito.
9. Não inclua explicações fora do JSON.

INSTRUÇÕES DO USUÁRIO:
{instrucoes_limpas}

REPORT_JSON ATUAL:
{_json_dump(report_json_atual)}
""".strip()

                try:
                    # Fallback curto: se a IA demorar, não derruba o reprocessamento.
                    result = await asyncio.wait_for(self.openai.run_inline_prompt_json(prompt), timeout=45)
                    novo_report_json = result.data
                except TimeoutError:
                    novo_report_json = copy.deepcopy(report_json_atual)
                    quality = novo_report_json.setdefault("quality", {})
                    warnings = quality.setdefault("warnings", [])
                    if isinstance(warnings, list):
                        warnings.append({
                            "tipo": "reprocessamento",
                            "descricao": "A instrução não foi reconhecida pela regra local e a IA excedeu o tempo limite. Nenhuma alteração foi aplicada.",
                        })
                    result = OpenAIJsonResult(
                        data=novo_report_json,
                        raw_text=_json_dump(novo_report_json),
                        model_used="fallback_timeout_sem_alteracao",
                    )
            else:
                result = OpenAIJsonResult(
                    data=novo_report_json,
                    raw_text=_json_dump(novo_report_json),
                    model_used="ajuste_local_deterministico",
                )
            _upsert_etapa(
                self.db,
                relatorio,
                *current_step,
                "concluido",
                input_json={"instrucoes": instrucoes_limpas},
                output_json={"report_json_reprocessado": novo_report_json},
                result=result,
            )
            self.db.commit()

            current_step = (80, "renderizacao_html_reprocessamento")
            _upsert_etapa(
                self.db,
                relatorio,
                *current_step,
                "processando",
                input_json={"fonte": "report_json_reprocessado"},
            )
            self.db.commit()

            relatorio.report_json = novo_report_json
            relatorio.html_path = render_report_html(relatorio.id, novo_report_json)
            relatorio.status = "concluido"
            self.db.add(relatorio)
            _upsert_etapa(
                self.db,
                relatorio,
                *current_step,
                "concluido",
                input_json={"fonte": "report_json_reprocessado"},
                output_json={"html_path": relatorio.html_path},
            )

            current_step = (90, "reprocessamento_concluido")
            _upsert_etapa(
                self.db,
                relatorio,
                *current_step,
                "concluido",
                output_json={"mensagem": "Relatório reprocessado com as instruções informadas."},
            )
            self.db.commit()
            self.db.refresh(relatorio)

            return {
                "relatorio_id": relatorio.id,
                "status": relatorio.status,
                "mensagem": "Relatório reprocessado com as instruções informadas.",
                "html_path": relatorio.html_path,
                "report_json": relatorio.report_json,
                "etapas": _etapas_response(self.db, relatorio.id),
            }
        except Exception as exc:  # noqa: BLE001
            relatorio.status = "erro"
            self.db.add(relatorio)
            if current_step:
                _upsert_etapa(
                    self.db,
                    relatorio,
                    current_step[0],
                    current_step[1],
                    "erro",
                    input_json={"instrucoes": instrucoes_limpas},
                    erro=str(exc),
                )
            _upsert_etapa(
                self.db,
                relatorio,
                99,
                "erro_reprocessamento",
                "erro",
                input_json={"relatorio_id": relatorio_id, "instrucoes": instrucoes_limpas},
                erro=str(exc),
            )
            self.db.commit()
            return {
                "relatorio_id": relatorio.id,
                "status": relatorio.status,
                "mensagem": "O reprocessamento encontrou um erro. Consulte o status da pipeline.",
                "erro": str(exc),
                "etapas": _etapas_response(self.db, relatorio.id),
            }

    async def processar(
        self,
        obra_id: int,
        numero_ata: str | None,
        data_referencia: date,
        arquivos: list[UploadFile] | None = None,
        conteudo_whatsapp: str | None = None,
        conteudo_transcricao: str | None = None,
        semana_referencia: str | None = None,
        observacoes: str | None = None,
    ) -> dict[str, Any]:
        """Execução síncrona mantida para compatibilidade/testes.

        A rota principal agora usa `iniciar_processamento` + background task para permitir
        status progressivo no frontend.
        """
        relatorio, stored_files = await self.iniciar_processamento(
            obra_id=obra_id,
            numero_ata=numero_ata,
            data_referencia=data_referencia,
            arquivos=arquivos,
        )
        await self.continuar_processamento(
            relatorio_id=relatorio.id,
            stored_files=stored_files,
            conteudo_whatsapp=conteudo_whatsapp,
            conteudo_transcricao=conteudo_transcricao,
            semana_referencia=semana_referencia,
            observacoes=observacoes,
        )
        self.db.refresh(relatorio)
        return {
            "relatorio_id": relatorio.id,
            "status": relatorio.status,
            "report_json": relatorio.report_json,
            "html_path": relatorio.html_path,
            "etapas": _etapas_response(self.db, relatorio.id),
        }


def parse_data_referencia(valor: str | date | None) -> date:
    parsed = safe_date(valor)
    if not parsed:
        raise ValueError("data_referencia inválida ou ausente.")
    return parsed
