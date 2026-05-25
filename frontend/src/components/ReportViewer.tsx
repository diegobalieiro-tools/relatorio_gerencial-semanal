import { relatorioHtmlUrl } from '../api/api';

type ReportViewerProps = {
  relatorioId: number;
};

export function ReportViewer({ relatorioId }: ReportViewerProps) {
  return (
    <div className="report-frame-wrap">
      <iframe className="report-frame" title="Relatório semanal renderizado" src={relatorioHtmlUrl(relatorioId)} />
    </div>
  );
}
