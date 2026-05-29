import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, type HistoricoItem, type Obra, type Relatorio } from '../api/api';
import { LinkButton } from '../components/Button';
import { Card } from '../components/Card';
import { KpiCard } from '../components/KpiCard';
import { PageTitle } from '../components/PageTitle';
import { StatusBadge } from '../components/StatusBadge';

function asText(value: unknown, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback;
  return String(value);
}

function formatDate(value: unknown) {
  const text = asText(value, '');
  if (!text) return '—';
  if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
    const [year, month, day] = text.slice(0, 10).split('-');
    return `${day}/${month}/${year}`;
  }
  return text;
}

function getStartDate(row: HistoricoItem) {
  return row.data_inicio || row.data_abertura || row.created_at || row.data_item || row.inicio || row.data_referencia;
}

function getEndDate(row: HistoricoItem) {
  return row.prazo || row.prazo_vigente || row.termino || row.data_fim || row.prazo_limite;
}

function isConcluido(row: HistoricoItem) {
  const status = String(row.status || '').toLowerCase();
  return status.includes('conclu');
}

function getPrazoStatus(row: HistoricoItem) {
  if (isConcluido(row)) return 'Concluído';
  const raw = getEndDate(row);
  const text = asText(raw, '');
  if (!text || !/^\d{4}-\d{2}-\d{2}/.test(text)) return 'Em andamento';

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const dueDate = new Date(`${text.slice(0, 10)}T00:00:00`);
  return dueDate < today ? 'Atrasado' : 'Em andamento';
}

function PendenciasAtivasTable({ rows }: { rows: HistoricoItem[] }) {
  const visibleRows = rows;

  if (!visibleRows.length) {
    return <div className="empty-state compact">Nenhuma pendência ativa registrada.</div>;
  }

  return (
    <div className="table-wrap compact-table-wrap">
      <table className="data-table compact-pendencias-table">
        <thead>
          <tr>
            <th>Pendência</th>
            <th>Data início</th>
            <th>Fim esperado</th>
            <th>Criticidade</th>
            <th>Responsável</th>
            <th>Status prazo</th>
          </tr>
        </thead>
        <tbody>
          {visibleRows.map((row) => {
            const prazoStatus = getPrazoStatus(row);
            return (
              <tr key={`${row.id}-${row.relatorio_id}-${row.titulo}`}>
                <td><strong>{asText(row.titulo || row.title)}</strong></td>
                <td>{formatDate(getStartDate(row))}</td>
                <td>{formatDate(getEndDate(row))}</td>
                <td>{asText(row.criticidade || row.nivel || row.priority)}</td>
                <td>{asText(row.responsavel || row.empresa_responsavel || row.responsible)}</td>
                <td><StatusBadge status={prazoStatus}>{prazoStatus}</StatusBadge></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function ObraDetalhePage() {
  const { obraId } = useParams();
  const id = Number(obraId);
  const [obra, setObra] = useState<Obra | null>(null);
  const [relatorios, setRelatorios] = useState<Relatorio[]>([]);
  const [pendencias, setPendencias] = useState<HistoricoItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let ignore = false;
    async function load() {
      try {
        setLoading(true);
        const [obraRes, relatoriosRes, pendenciasRes] = await Promise.all([
          api.get<Obra>(`/obras/${id}`),
          api.get<Relatorio[]>(`/obras/${id}/relatorios`),
          api.get<HistoricoItem[]>(`/obras/${id}/historico/pendencias`),
        ]);
        if (!ignore) {
          setObra(obraRes.data);
          setRelatorios(relatoriosRes.data);
          setPendencias(pendenciasRes.data);
        }
      } finally {
        if (!ignore) setLoading(false);
      }
    }
    if (id) load();
    return () => { ignore = true; };
  }, [id]);

  if (loading) return <div className="empty-state">Carregando obra...</div>;
  if (!obra) return <div className="empty-state">Obra não encontrada.</div>;

  return (
    <div className="detail-page">
      <PageTitle
        eyebrow="Obra"
        title={obra.nome}
        subtitle={`${obra.cliente} · Executora ${obra.executora} · ${obra.ano_vigente || 'Ano não informado'}`}
        actions={
          <div className="action-row">
            <LinkButton to={`/obras/${obra.id}/historico`} variant="secondary">Histórico</LinkButton>
            <LinkButton to={`/obras/${obra.id}/relatorios/novo`}>Novo Relatório</LinkButton>
          </div>
        }
      />

      <div className="kpi-grid kpi-grid--obra-detail">
        <KpiCard label="Relatórios gerados" value={relatorios.length} description="Relatórios vinculados à obra" />
        <KpiCard label="Pendências abertas" value={pendencias.length} description="Itens normalizados em histórico" />
        <KpiCard label="Última reunião" value={relatorios[0]?.data_referencia || 'Não informado'} description="Data do relatório mais recente" />
      </div>

      <div className="grid-two">
        <Card>
          <div className="section-heading">
            <h2>Últimos relatórios</h2>
            <Link to={`/obras/${obra.id}/relatorios/novo`}>Novo relatório</Link>
          </div>
          <div className="report-list">
            {relatorios.length ? relatorios.slice(0, 6).map((relatorio) => (
              <Link className="report-row" to={`/relatorios/${relatorio.id}`} key={relatorio.id}>
                <div>
                  <strong>{relatorio.titulo}</strong>
                  <span>{relatorio.numero_ata || 'Ata não informada'} · {relatorio.data_referencia}</span>
                </div>
                <StatusBadge status={relatorio.status}>{relatorio.status}</StatusBadge>
              </Link>
            )) : <div className="empty-state compact">Nenhum relatório gerado.</div>}
          </div>
        </Card>

        <Card>
          <div className="section-heading">
            <h2>Dados da obra</h2>
          </div>
          <div className="info-list">
            <p><span>Cliente</span><strong>{obra.cliente}</strong></p>
            <p><span>Gerenciadora</span><strong>{obra.gerenciadora}</strong></p>
            <p><span>Executora</span><strong>{obra.executora}</strong></p>
            <p><span>Engenheiro</span><strong>{obra.engenheiro_responsavel || 'Não informado'}</strong></p>
            <p><span>Prazo contratual</span><strong>{obra.prazo_contratual || 'Não informado'}</strong></p>
          </div>
        </Card>
      </div>

      <Card>
        <div className="section-heading">
          <div>
            <h2>Pendências abertas</h2>
            <p>Visão enxuta com prazo, responsável e situação calculada pela data atual.</p>
          </div>
        </div>
        <PendenciasAtivasTable rows={pendencias} />
      </Card>

    </div>
  );
}
