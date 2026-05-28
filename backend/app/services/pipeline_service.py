from __future__ import annotations

import json
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
from app.services.storage_service import build_files_context_text, save_uploads

PROMPT_1 = "prompt_01_leitura_visual_ocr_validacao.txt"
PROMPT_2 = "prompt_02_estruturacao_historico_analise.txt"
PROMPT_3 = "prompt_03_report_json_final.txt"

ETAPA_1 = "leitura_visual_ocr_validacao"
ETAPA_2 = "estruturacao_historico_analise"
ETAPA_3 = "report_json_final"
ETAPA_PERSISTENCIA = "persistencia_dados_historicos"
ETAPA_RENDER = "renderizacao_html"


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
    etapa.input_json = input_json
    etapa.output_json = output_json
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


class PipelineService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.openai = OpenAIService()

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

        try:
            stored_files = await save_uploads(self.db, relatorio.id, arquivos or [])
            self.db.commit()

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
                "ano_vigente": obra.ano_vigente or data_referencia.year,
                "data_reuniao_atual": data_referencia.isoformat(),
                "numero_ata": numero_ata or "",
                "prazo_contratual": obra.prazo_contratual.isoformat() if obra.prazo_contratual else "",
                "conteudo_whatsapp": conteudo_whatsapp or "",
                "conteudo_transcricao": conteudo_transcricao or "",
                "semana_referencia": semana_referencia or "",
                "observacoes": observacoes or "",
                **dictionaries,
            }

            step1_input = {
                **base_context,
                "arquivos_contexto_extraido": files_context_text,
            }
            _upsert_etapa(self.db, relatorio, 1, ETAPA_1, "processando", input_json=step1_input)
            self.db.commit()

            step1 = await self.openai.run_prompt_json(PROMPT_1, step1_input, files=stored_files)
            _upsert_etapa(
                self.db,
                relatorio,
                1,
                ETAPA_1,
                "concluido",
                input_json=step1_input,
                output_json=step1.data,
                result=step1,
            )
            self.db.commit()

            step2_input = {
                **base_context,
                "historico_anterior": _json_dump(history.get("ultimo_report_json_resumido", {})),
                "resumo_historico_normalizado": _json_dump(history),
                "extracao_validada": _json_dump(step1.data),
            }
            _upsert_etapa(self.db, relatorio, 2, ETAPA_2, "processando", input_json=step2_input)
            self.db.commit()

            step2 = await self.openai.run_prompt_json(PROMPT_2, step2_input)
            _upsert_etapa(
                self.db,
                relatorio,
                2,
                ETAPA_2,
                "concluido",
                input_json=step2_input,
                output_json=step2.data,
                result=step2,
            )
            self.db.commit()

            persist_result = persist_output_gpt2(self.db, obra.id, relatorio.id, step2.data)
            _upsert_etapa(
                self.db,
                relatorio,
                20,
                ETAPA_PERSISTENCIA,
                "concluido",
                input_json={"fonte": "output_gpt2"},
                output_json=persist_result.as_dict(),
            )
            self.db.commit()

            step3_input = {
                "dados_estruturados_analise": _json_dump(step2.data),
            }
            _upsert_etapa(self.db, relatorio, 3, ETAPA_3, "processando", input_json=step3_input)
            self.db.commit()

            step3 = await self.openai.run_prompt_json(PROMPT_3, step3_input)

            # O GPT3 gera o JSON final, mas não pode ser a única fonte de dados do HTML.
            # Em testes reais, ele pode resumir demais e retornar listas vazias
            # (pontos críticos, pendências, ambientes etc.). O adaptador abaixo recompõe
            # o report_json a partir do GPT2, preservando todas as informações já extraídas
            # e usa o GPT3 apenas como complemento visual/textual.
            # Enriquecemos o GPT 1 com o texto bruto extraído dos arquivos.
            # Isso permite que o report_adapter reconstrua deterministicamente a tabela completa
            # da ATA quando o GPT 1/2 resumirem ou omitirem linhas.
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
                3,
                ETAPA_3,
                "concluido",
                input_json=step3_input,
                output_json={"raw_gpt3": step3.data, "report_json_final": final_report_json},
                result=step3,
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
                30,
                ETAPA_RENDER,
                "concluido",
                input_json={"report_json": "relatorios_semanais.report_json"},
                output_json={"html_path": html_path},
            )
            self.db.commit()
            self.db.refresh(relatorio)

            return {
                "relatorio_id": relatorio.id,
                "status": relatorio.status,
                "report_json": relatorio.report_json,
                "html_path": relatorio.html_path,
                "etapas": [
                    {"etapa": 1, "nome": ETAPA_1, "status": "concluido"},
                    {"etapa": 2, "nome": ETAPA_2, "status": "concluido"},
                    {"etapa": 20, "nome": ETAPA_PERSISTENCIA, "status": "concluido"},
                    {"etapa": 3, "nome": ETAPA_3, "status": "concluido"},
                    {"etapa": 30, "nome": ETAPA_RENDER, "status": "concluido"},
                ],
            }

        except Exception as exc:  # noqa: BLE001
            relatorio.status = "erro"
            self.db.add(relatorio)
            _upsert_etapa(
                self.db,
                relatorio,
                99,
                "erro_pipeline",
                "erro",
                input_json={"obra_id": obra_id, "numero_ata": numero_ata, "data_referencia": str(data_referencia)},
                erro=str(exc),
            )
            self.db.commit()
            raise


def parse_data_referencia(valor: str | date | None) -> date:
    parsed = safe_date(valor)
    if not parsed:
        raise ValueError("data_referencia inválida ou ausente.")
    return parsed
