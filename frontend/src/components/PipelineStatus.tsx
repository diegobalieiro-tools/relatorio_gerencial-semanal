import type { PipelineEtapa } from '../api/api';
import { StatusBadge } from './StatusBadge';

const defaultSteps = [
  'Upload recebido',
  'GPT 1 — Leitura visual + OCR + validação',
  'GPT 2 — Estruturação + histórico + análise',
  'Persistência dos dados históricos',
  'GPT 3 — Report JSON final',
  'Renderização HTML',
  'Concluído',
];

type PipelineStatusProps = {
  status?: string;
  etapas?: PipelineEtapa[];
};

function labelFromEtapa(etapa: PipelineEtapa) {
  if (etapa.etapa_nome) return `${etapa.etapa_numero}. ${etapa.etapa_nome.replaceAll('_', ' ')}`;
  return `Etapa ${etapa.etapa_numero}`;
}

export function PipelineStatus({ status = 'pendente', etapas = [] }: PipelineStatusProps) {
  const rows = etapas.length
    ? etapas.map((etapa) => ({ label: labelFromEtapa(etapa), status: etapa.status, erro: etapa.erro }))
    : defaultSteps.map((label, index) => ({
        label,
        status: index === 0 && status !== 'pendente' ? status : 'pendente',
        erro: null as string | null,
      }));

  return (
    <div className="pipeline">
      <div className="pipeline__head">
        <h3>Status da pipeline</h3>
        <StatusBadge status={status}>{status}</StatusBadge>
      </div>
      <div className="pipeline__steps">
        {rows.map((step) => (
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
    </div>
  );
}
