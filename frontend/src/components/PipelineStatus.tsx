import type { PipelineEtapa } from '../api/api';
import { StatusBadge } from './StatusBadge';

const stepLabels: Record<string, string> = {
  upload_recebido: 'Upload recebido',
  leitura_visual_ocr_validacao: 'GPT 1 — Leitura visual + OCR + validação',
  estruturacao_historico_analise: 'GPT 2 — Estruturação + histórico + análise',
  persistencia_dados_historicos: 'Persistência dos dados históricos',
  report_json_final: 'GPT 3 — Report JSON final',
  renderizacao_html: 'Renderização HTML',
  concluido: 'Concluído',
  concluido_pipeline: 'Concluído',
  erro_pipeline: 'Erro na pipeline',
};

const defaultSteps = [
  { etapa_numero: 0, etapa_nome: 'upload_recebido' },
  { etapa_numero: 10, etapa_nome: 'leitura_visual_ocr_validacao' },
  { etapa_numero: 20, etapa_nome: 'estruturacao_historico_analise' },
  { etapa_numero: 30, etapa_nome: 'persistencia_dados_historicos' },
  { etapa_numero: 40, etapa_nome: 'report_json_final' },
  { etapa_numero: 50, etapa_nome: 'renderizacao_html' },
  { etapa_numero: 60, etapa_nome: 'concluido' },
];

type PipelineStatusProps = {
  status?: string;
  etapas?: PipelineEtapa[];
};

function normalizeStatus(status?: string | null) {
  const value = String(status || 'pendente').toLowerCase();
  if (value === 'concluida') return 'concluido';
  return value;
}

function labelFromEtapa(etapa: Pick<PipelineEtapa, 'etapa_nome' | 'etapa_numero'>) {
  if (etapa.etapa_nome && stepLabels[etapa.etapa_nome]) return stepLabels[etapa.etapa_nome];
  if (etapa.etapa_nome) return etapa.etapa_nome.replaceAll('_', ' ');
  return `Etapa ${etapa.etapa_numero}`;
}

export function PipelineStatus({ status = 'pendente', etapas = [] }: PipelineStatusProps) {
  const byName = new Map(etapas.map((etapa) => [etapa.etapa_nome, etapa]));
  const hasCustomError = etapas.some((etapa) => etapa.status === 'erro' && !byName.has(etapa.etapa_nome));

  const rows = defaultSteps.map((step, index) => {
    const etapa = byName.get(step.etapa_nome);
    if (etapa) {
      return {
        label: labelFromEtapa(etapa),
        status: normalizeStatus(etapa.status),
        erro: etapa.erro,
      };
    }

    const fallbackStatus = index === 0 && status !== 'pendente' ? normalizeStatus(status) : 'pendente';
    return {
      label: labelFromEtapa(step),
      status: fallbackStatus,
      erro: null as string | null,
    };
  });

  const extras = etapas
    .filter((etapa) => !defaultSteps.some((step) => step.etapa_nome === etapa.etapa_nome))
    .map((etapa) => ({ label: labelFromEtapa(etapa), status: normalizeStatus(etapa.status), erro: etapa.erro }));

  return (
    <div className="pipeline">
      <div className="pipeline__head">
        <div>
          <h3>Status da pipeline</h3>
          <p>Acompanhe cada etapa conforme o backend conclui o processamento.</p>
        </div>
        <StatusBadge status={status}>{status}</StatusBadge>
      </div>
      <div className="pipeline__steps">
        {[...rows, ...extras].map((step) => (
          <div className="pipeline__step" key={step.label}>
            <span className={`pipeline__dot pipeline__dot--${step.status}`} />
            <div>
              <p>{step.label}</p>
              {step.erro ? <small>{step.erro}</small> : null}
            </div>
            <StatusBadge status={step.status}>{step.status}</StatusBadge>
          </div>
        ))}
      </div>
      {hasCustomError ? <p className="pipeline__hint">Existe erro registrado em etapa adicional. Verifique o log do backend.</p> : null}
    </div>
  );
}
