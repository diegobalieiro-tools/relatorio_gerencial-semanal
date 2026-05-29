import { relatorioHtmlUrl } from '../api/api';

type ReportViewerProps = {
  relatorioId: number;
  cacheKey?: string | number;
};

export function ReportViewer({ relatorioId, cacheKey }: ReportViewerProps) {
  const suffix = cacheKey ? `?v=${encodeURIComponent(String(cacheKey))}` : '';

  return (
    <div className="report-frame-wrap">
      <iframe className="report-frame" title="Relatório semanal renderizado" src={`${relatorioHtmlUrl(relatorioId)}${suffix}`} />
    </div>
  );
}
