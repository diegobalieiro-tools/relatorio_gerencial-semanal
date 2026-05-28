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
