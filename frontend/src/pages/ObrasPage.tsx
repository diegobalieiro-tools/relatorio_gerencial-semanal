import { useEffect, useState } from 'react';
import { LinkButton } from '../components/Button';
import { ObraCard } from '../components/ObraCard';
import { PageTitle } from '../components/PageTitle';
import { api, type Obra } from '../api/api';

export function ObrasPage() {
  const [obras, setObras] = useState<Obra[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    async function load() {
      try {
        setLoading(true);
        const response = await api.get<Obra[]>('/obras');
        if (!ignore) setObras(response.data);
      } catch (err) {
        if (!ignore) setError('Não foi possível carregar as obras cadastradas.');
      } finally {
        if (!ignore) setLoading(false);
      }
    }
    load();
    return () => {
      ignore = true;
    };
  }, []);

  return (
    <div className="workspace-page">
      <PageTitle
        title="CVP Workspace"
        subtitle="Acompanhamento semanal de obras — Tools Engenharia"
        actions={<LinkButton to="/obras/nova">+ Nova Obra</LinkButton>}
      />

      {loading ? <div className="empty-state">Carregando obras...</div> : null}
      {error ? <div className="alert alert--error">{error}</div> : null}

      {!loading && !error && obras.length === 0 ? (
        <div className="empty-state">
          <h2>Nenhuma obra cadastrada</h2>
          <p>Crie a primeira obra para começar a gerar relatórios semanais.</p>
          <LinkButton to="/obras/nova">+ Nova Obra</LinkButton>
        </div>
      ) : null}

      <section className="obra-grid" aria-label="Obras cadastradas">
        {obras.map((obra) => <ObraCard key={obra.id} obra={obra} />)}
      </section>
    </div>
  );
}
