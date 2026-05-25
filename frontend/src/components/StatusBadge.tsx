import type { ReactNode } from 'react';

type StatusBadgeProps = {
  status?: string | null;
  children?: ReactNode;
};

const normalize = (status?: string | null) =>
  String(status || 'pendente')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/\s+/g, '-');

export function StatusBadge({ status, children }: StatusBadgeProps) {
  const key = normalize(status);
  return <span className={`status-badge status-badge--${key}`}>{children || status || 'Pendente'}</span>;
}
