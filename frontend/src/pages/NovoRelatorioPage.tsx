import { FormEvent, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, type Obra, type PipelineStatus as PipelineStatusType } from '../api/api';
import { Button, LinkButton } from '../components/Button';
import { Card } from '../components/Card';
import { Field, Input, Textarea } from '../components/FormControls';
import { PageTitle } from '../components/PageTitle';
import { PipelineStatus } from '../components/PipelineStatus';
import { UploadBox } from '../components/UploadBox';

type PipelineResponse = {
  relatorio_id: number;
  status: string;
  etapas?: Record<string, unknown>[];
};

export function NovoRelatorioPage() {
  const { obraId } = useParams();
  const navigate = useNavigate();
  const id = Number(obraId);

  const [obra, setObra] = useState<Obra | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [numeroAta, setNumeroAta] = useState('');
  const [dataReferencia, setDataReferencia] = useState('');
  const [semanaReferencia, setSemanaReferencia] = useState('');
  const [observacoes, setObservacoes] = useState('');
  const [conteudoWhatsapp, setConteudoWhatsapp] = useState('');
  const [conteudoTranscricao, setConteudoTranscricao] = useState('');
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PipelineResponse | null>(null);
  const [pipeline, setPipeline] = useState<PipelineStatusType | null>(null);

  useEffect(() => {
    if (!id) return;
    api.get<Obra>(`/obras/${id}`).then((response) => setObra(response.data));
  }, [id]);

  useEffect(() => {
    if (!result?.relatorio_id) return;
    const relatorioId = result.relatorio_id;
    let active = true;
    async function loadStatus() {
      try {
        const response = await api.get<PipelineStatusType>(`/pipeline/${relatorioId}/status`);
        if (active) setPipeline(response.data);
      } catch {
        // A pipeline pode terminar rápido e o status será carregado na tela do relatório.
      }
    }
    loadStatus();
    const timer = window.setInterval(loadStatus, 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [result?.relatorio_id]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setProcessing(true);
    setResult(null);
    setPipeline(null);

    try {
      const formData = new FormData();
      formData.append('obra_id', String(id));
      formData.append('numero_ata', numeroAta);
      formData.append('data_referencia', dataReferencia);
      formData.append('semana_referencia', semanaReferencia);
      formData.append('observacoes', observacoes);
      formData.append('conteudo_whatsapp', conteudoWhatsapp);
      formData.append('conteudo_transcricao', conteudoTranscricao);
      files.forEach((file) => formData.append('arquivos', file));

      const response = await api.post<PipelineResponse>('/pipeline/processar', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(response.data);
    } catch (err) {
      setError('Não foi possível processar o relatório. Verifique a API key, o banco e os arquivos enviados.');
    } finally {
      setProcessing(false);
    }
  }

  return (
    <div className="form-page">
      <PageTitle
        eyebrow={obra?.nome || 'Novo relatório'}
        title="Novo Relatório"
        subtitle="Envie atas, imagens, prints, Excel, conversas de WhatsApp e transcrições para gerar o relatório semanal com histórico e validações automáticas."
        actions={<LinkButton to={`/obras/${id}`} variant="secondary">Voltar para obra</LinkButton>}
      />

      {error ? <div className="alert alert--error">{error}</div> : null}

      <form onSubmit={handleSubmit}>
        <div className="grid-two align-start">
          <Card className="form-card">
            <h2>Dados básicos do relatório</h2>
            <div className="form-grid">
              <Field label="Obra selecionada">
                <Input value={obra?.nome || ''} disabled />
              </Field>
              <Field label="Número da ata">
                <Input value={numeroAta} onChange={(e) => setNumeroAta(e.target.value)} placeholder="Ex: 008" />
              </Field>
              <Field label="Data da reunião" required>
                <Input type="date" value={dataReferencia} onChange={(e) => setDataReferencia(e.target.value)} required />
              </Field>
              <Field label="Semana de referência">
                <Input value={semanaReferencia} onChange={(e) => setSemanaReferencia(e.target.value)} placeholder="Ex: Semana 21 / 2026" />
              </Field>
              <Field label="Observações adicionais" className="span-2">
                <Textarea rows={4} value={observacoes} onChange={(e) => setObservacoes(e.target.value)} />
              </Field>
            </div>
          </Card>

          <Card>
            <UploadBox files={files} onFilesChange={setFiles} />
          </Card>
        </div>

        <Card className="form-card mt-24">
          <h2>Fontes complementares</h2>
          <div className="form-grid">
            <Field label="Conversas de WhatsApp" className="span-2">
              <Textarea rows={8} value={conteudoWhatsapp} onChange={(e) => setConteudoWhatsapp(e.target.value)} placeholder="Cole aqui as mensagens relevantes da semana." />
            </Field>
            <Field label="Transcrição de reunião" className="span-2">
              <Textarea rows={8} value={conteudoTranscricao} onChange={(e) => setConteudoTranscricao(e.target.value)} placeholder="Cole aqui a transcrição ou resumo da reunião." />
            </Field>
          </div>
        </Card>

        <div className="form-actions">
          <Button type="submit" disabled={processing}>{processing ? 'Processando...' : 'Processar relatório'}</Button>
        </div>
      </form>

      <Card className="mt-24">
        <PipelineStatus status={processing ? 'processando' : result?.status || 'pendente'} etapas={pipeline?.etapas || []} />
        {result?.relatorio_id ? (
          <div className="result-box">
            <strong>Relatório criado com sucesso.</strong>
            <p>ID: {result.relatorio_id}</p>
            <div className="action-row">
              <Button onClick={() => navigate(`/relatorios/${result.relatorio_id}`)}>Abrir relatório</Button>
              <Link to={`/obras/${id}`}>Voltar para obra</Link>
            </div>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
