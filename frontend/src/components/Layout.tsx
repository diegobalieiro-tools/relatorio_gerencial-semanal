import type { PropsWithChildren } from 'react';
import { NavLink } from 'react-router-dom';

export function Layout({ children }: PropsWithChildren) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__inner">
          <NavLink to="/obras" className="brand-link" aria-label="Ir para obras">
            <span className="tools-wordmark">TOOLS</span>
            <span className="brand-divider" />
            <span className="brand-subtitle">CVP · Acompanhamento Semanal</span>
          </NavLink>
          <nav className="app-nav" aria-label="Navegação principal">
            <NavLink to="/obras">Obras</NavLink>
            <NavLink to="/dicionarios">Dicionários</NavLink>
          </nav>
        </div>
      </header>
      <main className="app-main">{children}</main>
    </div>
  );
}
