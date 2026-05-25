import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, type HistoricoItem, type Obra, type Relatorio } from '../api/api';
import { LinkButton } from '../components/Button';
import { Card } from '../components/Card';
import { DataTable } from '../components/DataTable';
import { KpiCard } from '../components/KpiCard';
import { PageTitle } from '../components/PageTitle';
import { StatusBadge } from '../components/StatusBadge';

export function ObraDetalhePage() {
  const { obraId } = useParams();
  const id = Number(obraId);
  const [obra, setObra] = useState<Obra | null>(null);
  const [relatorios, setRelatorios] = useState<Relatorio[]>([]);
  const [pendencias, setPendencias] = useState<HistoricoItem[]>([]);
  const [pontos, setPontos] = useState<HistoricoItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let ignore = false;
    async function load() {
      try {
        setLoading(true);
        const [obraRes, relatoriosRes, pendenciasRes, pontosRes] = await Promise.all([
          api.get<Obra>(`/obras/${id}`),
          api.get<Relatorio[]>(`/obras/${id}/relatorios`),
          api.get<HistoricoItem[]>(`/obras/${id}/historico/pendencias`),
          api.get<HistoricoItem[]>(`/obras/${id}/historico/pontos-criticos`),
        ]);
        if (!ignore) {
          setObra(obraRes.data);
          setRelatorios(relatoriosRes.data);
          setPendencias(pendenciasRes.data);
          setPontos(pontosRes.data);
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

      <div className="kpi-grid">
        <KpiCard label="Relatórios gerados" value={relatorios.length} description="Relatórios vinculados à obra" />
        <KpiCard label="Pendências abertas" value={pendencias.length} description="Itens normalizados em histórico" />
        <KpiCard label="Pontos críticos ativos" value={pontos.length} description="Pontos críticos recentes" />
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
        <div className="section-heading"><h2>Pendências abertas</h2></div>
        <DataTable rows={pendencias.slice(0, 8)} />
      </Card>

      <Card>
        <div className="section-heading"><h2>Pontos críticos recorrentes</h2></div>
        <DataTable rows={pontos.slice(0, 8)} />
      </Card>
    </div>
  );
}
