import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { ObrasPage } from './pages/ObrasPage';
import { NovaObraPage } from './pages/NovaObraPage';
import { ObraDetalhePage } from './pages/ObraDetalhePage';
import { NovoRelatorioPage } from './pages/NovoRelatorioPage';
import { RelatorioDetalhePage } from './pages/RelatorioDetalhePage';
import { HistoricoDadosPage } from './pages/HistoricoDadosPage';
import { DicionariosPage } from './pages/DicionariosPage';

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/obras" replace />} />
        <Route path="/obras" element={<ObrasPage />} />
        <Route path="/obras/nova" element={<NovaObraPage />} />
        <Route path="/obras/:obraId" element={<ObraDetalhePage />} />
        <Route path="/obras/:obraId/relatorios/novo" element={<NovoRelatorioPage />} />
        <Route path="/relatorios/:relatorioId" element={<RelatorioDetalhePage />} />
        <Route path="/obras/:obraId/historico" element={<HistoricoDadosPage />} />
        <Route path="/dicionarios" element={<DicionariosPage />} />
      </Routes>
    </Layout>
  );
}
