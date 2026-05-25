import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, type Obra, type ObraPayload } from '../api/api';
import { Button, LinkButton } from '../components/Button';
import { Card } from '../components/Card';
import { Field, Input, Textarea } from '../components/FormControls';
import { PageTitle } from '../components/PageTitle';

const currentYear = new Date().getFullYear();

export function NovaObraPage() {
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<ObraPayload>({
    nome: '',
    cliente: '',
    executora: '',
    gerenciadora: 'TOOLS',
    ano_vigente: currentYear,
    engenheiro_responsavel: '',
    prazo_contratual: '',
    observacoes: '',
  });

  function update<K extends keyof ObraPayload>(field: K, value: ObraPayload[K]) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSaving(true);

    try {
      const payload: ObraPayload = {
        ...form,
        ano_vigente: form.ano_vigente ? Number(form.ano_vigente) : null,
        prazo_contratual: form.prazo_contratual || null,
        engenheiro_responsavel: form.engenheiro_responsavel || null,
        observacoes: form.observacoes || null,
      };
      const response = await api.post<Obra>('/obras', payload);
      navigate(`/obras/${response.data.id}`);
    } catch (err) {
      setError('Não foi possível criar a obra. Verifique os campos obrigatórios.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="form-page narrow">
      <PageTitle
        title="Nova Obra"
        subtitle="Informe os dados básicos da obra. O restante, como itens, riscos, prazos e pendências, será extraído automaticamente pela IA a partir das atas e transcrições enviadas em cada relatório semanal."
        actions={<LinkButton to="/obras" variant="secondary">Voltar</LinkButton>}
      />

      {error ? <div className="alert alert--error">{error}</div> : null}

      <form onSubmit={handleSubmit}>
        <Card className="form-card">
          <h2>Identificação</h2>
          <div className="form-grid form-grid--full">
            <Field label="Nome da obra" required className="span-2">
              <Input value={form.nome} onChange={(e) => update('nome', e.target.value)} required />
            </Field>
            <Field label="Cliente" required>
              <Input value={form.cliente} onChange={(e) => update('cliente', e.target.value)} required />
            </Field>
            <Field label="Construtora / executora" required>
              <Input value={form.executora} onChange={(e) => update('executora', e.target.value)} required />
            </Field>
            <Field label="Gerenciadora">
              <Input value={form.gerenciadora} onChange={(e) => update('gerenciadora', e.target.value)} />
            </Field>
            <Field label="Ano vigente">
              <Input type="number" value={form.ano_vigente || ''} onChange={(e) => update('ano_vigente', Number(e.target.value))} />
            </Field>
            <Field label="Engenheiro responsável">
              <Input value={form.engenheiro_responsavel || ''} onChange={(e) => update('engenheiro_responsavel', e.target.value)} />
            </Field>
            <Field label="Prazo contratual">
              <Input type="date" value={form.prazo_contratual || ''} onChange={(e) => update('prazo_contratual', e.target.value)} />
            </Field>
            <Field label="Observações" className="span-2">
              <Textarea rows={4} value={form.observacoes || ''} onChange={(e) => update('observacoes', e.target.value)} />
            </Field>
          </div>
        </Card>

        <div className="form-actions">
          <Button type="submit" disabled={saving}>{saving ? 'Criando...' : 'Criar obra'}</Button>
        </div>
      </form>
    </div>
  );
}
