import type { PropsWithChildren, HTMLAttributes } from 'react';

type CardProps = PropsWithChildren<HTMLAttributes<HTMLDivElement>>;

export function Card({ children, className = '', ...props }: CardProps) {
  return (
    <div className={['card', className].filter(Boolean).join(' ')} {...props}>
      {children}
    </div>
  );
}
