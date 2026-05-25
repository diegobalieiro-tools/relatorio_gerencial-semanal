import { Link } from 'react-router-dom';
import type { Obra } from '../api/api';

type ObraCardProps = {
  obra: Obra;
};

export function ObraCard({ obra }: ObraCardProps) {
  return (
    <Link className="obra-card" to={`/obras/${obra.id}`}>
      <div className="obra-card__top">
        <span className="obra-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M4 21h16" />
            <path d="M6 21V9l6-3 6 3v12" />
            <path d="M9 21v-7h6v7" />
            <path d="M9 10h.01M12 10h.01M15 10h.01" />
          </svg>
        </span>
        <span className="obra-card__year">{obra.ano_vigente || '—'}</span>
      </div>
      <h2>{obra.nome}</h2>
      <p className="obra-card__client">{obra.cliente}</p>
      <div className="obra-card__line" />
      <p className="obra-card__meta">Executora: <strong>{obra.executora}</strong></p>
      <div className="obra-card__footer">
        <span>{obra.relatorios_count || 0} relatórios</span>
        <span>{obra.ultimo_relatorio ? `Último: ${obra.ultimo_relatorio}` : 'Sem relatório'}</span>
      </div>
    </Link>
  );
}
