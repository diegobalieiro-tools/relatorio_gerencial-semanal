import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api, type HistoricoItem, type Obra } from '../api/api';
import { Card } from '../components/Card';
import { DataTable } from '../components/DataTable';
import { Field, Input, Select } from '../components/FormControls';
import { PageTitle } from '../components/PageTitle';
import { LinkButton } from '../components/Button';

type HistoricoMap = {
  pendencias: HistoricoItem[];
  pontos: HistoricoItem[];
  reprogramacoes: HistoricoItem[];
  itens: HistoricoItem[];
};

const initialData: HistoricoMap = {
  pendencias: [],
  pontos: [],
  reprogramacoes: [],
  itens: [],
};

export function HistoricoDadosPage() {
  const { obraId } = useParams();
  const id = Number(obraId);
  const [obra, setObra] = useState<Obra | null>(null);
  const [data, setData] = useState<HistoricoMap>(initialData);
  const [active, setActive] = useState<keyof HistoricoMap>('pendencias');
  const [query, setQuery] = useState('');
  const [criticidade, setCriticidade] = useState('');

  useEffect(() => {
    let ignore = false;
    async function load() {
      const [obraRes, pendenciasRes, pontosRes, reprogramacoesRes, itensRes] = await Promise.all([
        api.get<Obra>(`/obras/${id}`),
        api.get<HistoricoItem[]>(`/obras/${id}/historico/pendencias`),
        api.get<HistoricoItem[]>(`/obras/${id}/historico/pontos-criticos`),
        api.get<HistoricoItem[]>(`/obras/${id}/historico/reprogramacoes`),
        api.get<HistoricoItem[]>(`/obras/${id}/historico/itens`),
      ]);
      if (!ignore) {
        setObra(obraRes.data);
        setData({
          pendencias: pendenciasRes.data,
          pontos: pontosRes.data,
          reprogramacoes: reprogramacoesRes.data,
          itens: itensRes.data,
        });
      }
    }
    if (id) load();
    return () => { ignore = true; };
  }, [id]);

  const filteredRows = useMemo(() => {
    const rows = data[active];
    return rows.filter((row) => {
      const asText = JSON.stringify(row).toLowerCase();
      const matchQuery = query ? asText.includes(query.toLowerCase()) : true;
      const matchCrit = criticidade ? asText.includes(criticidade.toLowerCase()) : true;
      return matchQuery && matchCrit;
    });
  }, [active, data, query, criticidade]);

  return (
    <div className="history-page">
      <PageTitle
        eyebrow={obra?.nome || 'Histórico'}
        title="Histórico da Obra"
        subtitle="Consulta dos dados normalizados: pendências, pontos críticos, reprogramações, itens de acompanhamento e evolução de status."
        actions={<LinkButton to={`/obras/${id}`} variant="secondary">Voltar para obra</LinkButton>}
      />

      <Card>
        <div className="history-tabs">
          <button className={active === 'pendencias' ? 'is-active' : ''} onClick={() => setActive('pendencias')}>Pendências</button>
          <button className={active === 'pontos' ? 'is-active' : ''} onClick={() => setActive('pontos')}>Pontos críticos</button>
          <button className={active === 'reprogramacoes' ? 'is-active' : ''} onClick={() => setActive('reprogramacoes')}>Reprogramações</button>
          <button className={active === 'itens' ? 'is-active' : ''} onClick={() => setActive('itens')}>Itens</button>
        </div>

        <div className="filters">
          <Field label="Buscar">
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Responsável, título, status..." />
          </Field>
          <Field label="Criticidade">
            <Select value={criticidade} onChange={(e) => setCriticidade(e.target.value)}>
              <option value="">Todas</option>
              <option value="crítica">Crítica</option>
              <option value="alta">Alta</option>
              <option value="média">Média</option>
              <option value="baixa">Baixa</option>
            </Select>
          </Field>
        </div>

        <DataTable rows={filteredRows} />
      </Card>
    </div>
  );
}
