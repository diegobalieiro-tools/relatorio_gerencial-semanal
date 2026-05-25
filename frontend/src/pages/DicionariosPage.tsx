import { useEffect, useState } from 'react';
import { api, type DictionaryResponse } from '../api/api';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { Textarea } from '../components/FormControls';
import { PageTitle } from '../components/PageTitle';

export function DicionariosPage() {
  const [ocr, setOcr] = useState('');
  const [context, setContext] = useState('');
  const [saving, setSaving] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    async function load() {
      const [ocrRes, contextRes] = await Promise.all([
        api.get<DictionaryResponse>('/dictionaries/ocr'),
        api.get<DictionaryResponse>('/dictionaries/context'),
      ]);
      if (!ignore) {
        setOcr(ocrRes.data.content);
        setContext(contextRes.data.content);
      }
    }
    load();
    return () => { ignore = true; };
  }, []);

  async function save(kind: 'ocr' | 'context') {
    setSaving(kind);
    setMessage(null);
    const content = kind === 'ocr' ? ocr : context;
    await api.put(`/dictionaries/${kind}`, { content });
    setSaving(null);
    setMessage(kind === 'ocr' ? 'Dicionário OCR salvo.' : 'Termos de contexto salvos.');
  }

  return (
    <div className="dictionaries-page">
      <PageTitle
        title="Dicionários"
        subtitle="Arquivos utilizados como contexto na leitura visual/OCR da etapa GPT 1."
      />

      {message ? <div className="alert alert--success">{message}</div> : null}

      <div className="grid-two align-start">
        <Card className="dictionary-card">
          <div className="section-heading">
            <div>
              <h2>Erros comuns de OCR</h2>
              <p>backend/app/data/dictionaries/ocr_common_errors.txt</p>
            </div>
            <Button size="sm" onClick={() => save('ocr')} disabled={saving === 'ocr'}>
              {saving === 'ocr' ? 'Salvando...' : 'Salvar'}
            </Button>
          </div>
          <Textarea rows={22} value={ocr} onChange={(e) => setOcr(e.target.value)} />
        </Card>

        <Card className="dictionary-card">
          <div className="section-heading">
            <div>
              <h2>Termos de contexto</h2>
              <p>backend/app/data/dictionaries/context_terms.txt</p>
            </div>
            <Button size="sm" onClick={() => save('context')} disabled={saving === 'context'}>
              {saving === 'context' ? 'Salvando...' : 'Salvar'}
            </Button>
          </div>
          <Textarea rows={22} value={context} onChange={(e) => setContext(e.target.value)} />
        </Card>
      </div>
    </div>
  );
}
