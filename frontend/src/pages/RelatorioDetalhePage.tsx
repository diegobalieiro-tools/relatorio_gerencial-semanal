import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api, relatorioDownloadUrl, type PipelineStatus as PipelineStatusType, type Relatorio } from '../api/api';
import { Button, LinkButton } from '../components/Button';
import { Card } from '../components/Card';
import { PageTitle } from '../components/PageTitle';
import { PipelineStatus } from '../components/PipelineStatus';
import { ReportViewer } from '../components/ReportViewer';
import { StatusBadge } from '../components/StatusBadge';

export function RelatorioDetalhePage() {
  const { relatorioId } = useParams();
  const id = Number(relatorioId);
  const [relatorio, setRelatorio] = useState<Relatorio | null>(null);
  const [pipeline, setPipeline] = useState<PipelineStatusType | null>(null);
  const [showJson, setShowJson] = useState(false);
  const [showPreview, setShowPreview] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    async function load() {
      const [relatorioRes, pipelineRes] = await Promise.all([
        api.get<Relatorio>(`/relatorios/${id}`),
        api.get<PipelineStatusType>(`/pipeline/${id}/status`),
      ]);
      if (!ignore) {
        setRelatorio(relatorioRes.data);
        setPipeline(pipelineRes.data);
      }
    }
    if (id) load();
    return () => { ignore = true; };
  }, [id]);

  async function reprocessar() {
    setMessage(null);
    const response = await api.post<{ mensagem?: string; status: string }>(`/pipeline/${id}/reprocessar`);
    setMessage(response.data.mensagem || response.data.status);
  }

  if (!relatorio) return <div className="empty-state">Carregando relatório...</div>;

  return (
    <div className="detail-page">
      <PageTitle
        eyebrow={`Relatório #${relatorio.id}`}
        title={relatorio.titulo}
        subtitle={`${relatorio.numero_ata || 'Ata não informada'} · Referência ${relatorio.data_referencia}`}
        actions={
          <div className="action-row">
            <LinkButton to={`/obras/${relatorio.obra_id}`} variant="secondary">Obra</LinkButton>
            <a className="btn btn--primary btn--md" href={relatorioDownloadUrl(relatorio.id)}>Baixar HTML</a>
          </div>
        }
      />

      {message ? <div className="alert">{message}</div> : null}

      <div className="grid-two align-start">
        <Card>
          <div className="section-heading">
            <h2>Status do processamento</h2>
            <StatusBadge status={relatorio.status}>{relatorio.status}</StatusBadge>
          </div>
          <PipelineStatus status={pipeline?.status || relatorio.status} etapas={pipeline?.etapas || relatorio.etapas || []} />
        </Card>

        <Card>
          <div className="section-heading"><h2>Ações</h2></div>
          <div className="button-stack">
            <Button variant="secondary" onClick={() => setShowPreview((prev) => !prev)}>
              {showPreview ? 'Ocultar visualização' : 'Visualizar relatório'}
            </Button>
            <Button variant="secondary" onClick={() => setShowJson((prev) => !prev)}>
              {showJson ? 'Ocultar JSON final' : 'Visualizar JSON final'}
            </Button>
            <Button variant="ghost" onClick={reprocessar}>Reprocessar</Button>
          </div>
        </Card>
      </div>

      {showPreview ? (
        <Card className="mt-24 report-card">
          <div className="section-heading"><h2>Preview do relatório HTML</h2></div>
          <ReportViewer relatorioId={relatorio.id} />
        </Card>
      ) : null}

      {showJson ? (
        <Card className="mt-24">
          <div className="section-heading"><h2>JSON final para auditoria</h2></div>
          <pre className="json-viewer">{JSON.stringify(relatorio.report_json || {}, null, 2)}</pre>
        </Card>
      ) : null}
    </div>
  );
}
