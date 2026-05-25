import type { ReactNode } from 'react';

type PageTitleProps = {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
};

export function PageTitle({ eyebrow, title, subtitle, actions }: PageTitleProps) {
  return (
    <div className="page-title">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {subtitle ? <p className="page-title__subtitle">{subtitle}</p> : null}
      </div>
      {actions ? <div className="page-title__actions">{actions}</div> : null}
    </div>
  );
}
