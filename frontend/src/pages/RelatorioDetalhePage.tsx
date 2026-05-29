import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api, relatorioDownloadUrl, type PipelineEtapa, type PipelineStatus as PipelineStatusType, type Relatorio } from '../api/api';
import { Button, LinkButton } from '../components/Button';
import { Card } from '../components/Card';
import { PageTitle } from '../components/PageTitle';
import { PipelineStatus } from '../components/PipelineStatus';
import { ReportViewer } from '../components/ReportViewer';
import { StatusBadge } from '../components/StatusBadge';

function isFinalStatus(status?: string | null) {
  const normalized = String(status || '').toLowerCase();
  return normalized === 'concluido' || normalized === 'concluida' || normalized === 'erro';
}

function isReprocessStep(etapa: PipelineEtapa) {
  return etapa.etapa_numero >= 70 || String(etapa.etapa_nome || '').includes('reprocess');
}

function calculateReprocessProgress(etapas: PipelineEtapa[] = []) {
  const reprocessSteps = etapas.filter(isReprocessStep).filter((etapa) => etapa.etapa_numero !== 99);
  if (!reprocessSteps.length) return 0;

  const total = Math.max(reprocessSteps.length, 3);
  const score = reprocessSteps.reduce((acc, etapa) => {
    const status = String(etapa.status || '').toLowerCase();
    if (status === 'concluido' || status === 'concluida') return acc + 1;
    if (status === 'processando' || status === 'reprocessando') return acc + 0.45;
    return acc;
  }, 0);

  return Math.max(5, Math.min(100, Math.round((score / total) * 100)));
}

export function RelatorioDetalhePage() {
  const { relatorioId } = useParams();
  const id = Number(relatorioId);
  const [relatorio, setRelatorio] = useState<Relatorio | null>(null);
  const [pipeline, setPipeline] = useState<PipelineStatusType | null>(null);
  const [showJson, setShowJson] = useState(false);
  const [showPreview, setShowPreview] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reprocessInstructions, setReprocessInstructions] = useState('');
  const [isReprocessing, setIsReprocessing] = useState(false);
  const [previewVersion, setPreviewVersion] = useState(() => Date.now());

  async function load() {
    const [relatorioRes, pipelineRes] = await Promise.all([
      api.get<Relatorio>(`/relatorios/${id}`),
      api.get<PipelineStatusType>(`/pipeline/${id}/status`),
    ]);
    setRelatorio(relatorioRes.data);
    setPipeline(pipelineRes.data);
    return { relatorio: relatorioRes.data, pipeline: pipelineRes.data };
  }

  useEffect(() => {
    let ignore = false;
    async function loadInitial() {
      const [relatorioRes, pipelineRes] = await Promise.all([
        api.get<Relatorio>(`/relatorios/${id}`),
        api.get<PipelineStatusType>(`/pipeline/${id}/status`),
      ]);
      if (!ignore) {
        setRelatorio(relatorioRes.data);
        setPipeline(pipelineRes.data);
      }
    }
    if (id) loadInitial();
    return () => { ignore = true; };
  }, [id]);

  const reprocessEtapas = useMemo(() => (pipeline?.etapas || []).filter(isReprocessStep), [pipeline?.etapas]);
  const hasRunningReprocessStep = reprocessEtapas.some((etapa) => String(etapa.status || '').toLowerCase() === 'processando');
  const isReprocessInProgress =
    isReprocessing ||
    String(pipeline?.status || '').toLowerCase() === 'reprocessando' ||
    String(relatorio?.status || '').toLowerCase() === 'reprocessando' ||
    hasRunningReprocessStep;
  const reprocessProgress = useMemo(() => calculateReprocessProgress(pipeline?.etapas || []), [pipeline?.etapas]);

  useEffect(() => {
    if (!id || !isReprocessInProgress) return undefined;

    const interval = window.setInterval(async () => {
      try {
        const result = await load();
        const status = String(result.pipeline.status || result.relatorio.status || '').toLowerCase();
        const activeStep = (result.pipeline.etapas || [])
          .filter(isReprocessStep)
          .some((etapa) => String(etapa.status || '').toLowerCase() === 'processando');
        if (isFinalStatus(status) && !activeStep) {
          setIsReprocessing(false);
          setPreviewVersion(Date.now());
          if (status === 'concluido') {
            setMessage('Relatório reprocessado com sucesso. A prévia foi atualizada.');
            setShowPreview(true);
          }
          if (status === 'erro') {
            setError('O reprocessamento encontrou um erro. Verifique o status da pipeline.');
          }
        }
      } catch {
        // Mantém o polling ativo; o próximo ciclo tenta novamente.
      }
    }, 2000);

    return () => window.clearInterval(interval);
  }, [id, isReprocessInProgress]);

  async function reprocessar() {
    const instrucoes = reprocessInstructions.trim();
    setMessage(null);
    setError(null);

    if (!instrucoes) {
      setError('Descreva as mudanças desejadas antes de reprocessar.');
      return;
    }

    try {
      setIsReprocessing(true);
      const response = await api.post<{ mensagem?: string; status: string; etapas?: PipelineEtapa[] }>(`/pipeline/${id}/reprocessar`, {
        instrucoes,
      });
      setMessage(response.data.mensagem || 'Reprocessamento iniciado. Acompanhe o progresso.');
      setShowPreview(true);
      setRelatorio((current) => current ? { ...current, status: response.data.status || 'reprocessando' } : current);
      if (response.data.etapas) {
        setPipeline({ relatorio_id: id, status: response.data.status || 'reprocessando', etapas: response.data.etapas });
      }
      await load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || 'Não foi possível reprocessar o relatório.');
      setIsReprocessing(false);
    }
  }

  if (!relatorio) return <div className="empty-state">Carregando relatório...</div>;

  return (
    <div className="detail-page report-detail-page">
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

      {message ? <div className="alert alert--success">{message}</div> : null}
      {error ? <div className="alert alert--error">{error}</div> : null}

      <div className="grid-two align-start report-detail-grid">
        <Card>
          <div className="section-heading">
            <h2>Status do processamento</h2>
            <StatusBadge status={pipeline?.status || relatorio.status}>{pipeline?.status || relatorio.status}</StatusBadge>
          </div>
          <PipelineStatus status={pipeline?.status || relatorio.status} etapas={pipeline?.etapas || relatorio.etapas || []} />
        </Card>

        <Card>
          <div className="section-heading">
            <div>
              <h2>Ações</h2>
              <p>Use o campo abaixo para solicitar ajustes pontuais antes de reprocessar o HTML.</p>
            </div>
          </div>
          <div className="button-stack">
            <Button variant="secondary" onClick={() => setShowPreview((prev) => !prev)} disabled={isReprocessInProgress}>
              {showPreview ? 'Ocultar visualização' : 'Visualizar relatório'}
            </Button>
            <Button variant="secondary" onClick={() => setShowJson((prev) => !prev)} disabled={isReprocessInProgress}>
              {showJson ? 'Ocultar JSON final' : 'Visualizar JSON final'}
            </Button>
            <label className="field reprocess-field">
              <span className="field__label">Instruções para reprocessar</span>
              <span className="field__hint">Ex.: remover uma seção, inserir uma observação complementar, reforçar uma pendência ou ajustar uma análise.</span>
              <textarea
                className="textarea"
                value={reprocessInstructions}
                onChange={(event) => setReprocessInstructions(event.target.value)}
                placeholder="Descreva aqui as mudanças desejadas para o relatório..."
                disabled={isReprocessInProgress}
              />
            </label>

            {isReprocessInProgress ? (
              <div className="reprocess-progress" aria-live="polite">
                <div className="reprocess-progress__top">
                  <strong>Reprocessando relatório</strong>
                  <span>{reprocessProgress}%</span>
                </div>
                <div className="reprocess-progress__bar"><span style={{ width: `${reprocessProgress}%` }} /></div>
                <p>
                  {reprocessEtapas.find((etapa) => etapa.status === 'processando')?.etapa_nome?.replaceAll('_', ' ') || 'Aguardando atualização do backend...'}
                </p>
              </div>
            ) : null}

            <Button variant="ghost" onClick={reprocessar} disabled={isReprocessInProgress}>
              {isReprocessInProgress ? 'Reprocessando...' : 'Reprocessar com instruções'}
            </Button>
          </div>
        </Card>
      </div>

      {showPreview ? (
        <Card className="mt-24 report-card report-card--wide">
          <div className="section-heading"><h2>Preview do relatório HTML</h2></div>
          <ReportViewer relatorioId={relatorio.id} cacheKey={previewVersion} />
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
