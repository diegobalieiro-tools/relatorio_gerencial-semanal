import axios from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

export const api = axios.create({
  baseURL: API_BASE_URL,
});

export type Obra = {
  id: number;
  nome: string;
  cliente: string;
  executora: string;
  gerenciadora: string;
  ano_vigente?: number | null;
  engenheiro_responsavel?: string | null;
  prazo_contratual?: string | null;
  observacoes?: string | null;
  dicionario_tecnico_json?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  relatorios_count?: number;
  ultimo_relatorio?: string | null;
};

export type ObraPayload = {
  nome: string;
  cliente: string;
  executora: string;
  gerenciadora: string;
  ano_vigente?: number | null;
  engenheiro_responsavel?: string | null;
  prazo_contratual?: string | null;
  observacoes?: string | null;
};

export type Relatorio = {
  id: number;
  obra_id: number;
  numero_ata?: string | null;
  data_referencia: string;
  titulo: string;
  status: string;
  report_json?: Record<string, unknown> | null;
  html_path?: string | null;
  template_version?: string;
  created_at?: string;
  updated_at?: string;
  etapas?: PipelineEtapa[];
};

export type PipelineEtapa = {
  id?: number;
  etapa_numero: number;
  etapa_nome: string;
  status: string;
  erro?: string | null;
  modelo_usado?: string | null;
  tokens_entrada?: number | null;
  tokens_saida?: number | null;
  updated_at?: string;
};

export type PipelineStatus = {
  relatorio_id: number;
  status: string;
  etapas: PipelineEtapa[];
};

export type DictionaryResponse = {
  name: 'ocr' | 'context';
  content: string;
};

export type HistoricoItem = Record<string, string | number | boolean | null | undefined>;

export function relatorioHtmlUrl(relatorioId: number | string) {
  return `${API_BASE_URL}/relatorios/${relatorioId}/html`;
}

export function relatorioDownloadUrl(relatorioId: number | string) {
  return `${API_BASE_URL}/relatorios/${relatorioId}/download`;
}
