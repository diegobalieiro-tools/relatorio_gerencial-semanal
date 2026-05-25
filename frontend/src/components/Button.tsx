import type { ButtonHTMLAttributes, AnchorHTMLAttributes, PropsWithChildren } from 'react';
import { Link } from 'react-router-dom';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md';

type BaseProps = PropsWithChildren<{
  variant?: Variant;
  size?: Size;
  className?: string;
}>;

type ButtonProps = BaseProps & ButtonHTMLAttributes<HTMLButtonElement>;
type LinkButtonProps = BaseProps & AnchorHTMLAttributes<HTMLAnchorElement> & { to: string };

function classes(variant: Variant = 'primary', size: Size = 'md', className = '') {
  return ['btn', `btn--${variant}`, `btn--${size}`, className].filter(Boolean).join(' ');
}

export function Button({ children, variant = 'primary', size = 'md', className, ...props }: ButtonProps) {
  return (
    <button className={classes(variant, size, className)} {...props}>
      {children}
    </button>
  );
}

export function LinkButton({ children, variant = 'primary', size = 'md', className, to, ...props }: LinkButtonProps) {
  return (
    <Link className={classes(variant, size, className)} to={to} {...props}>
      {children}
    </Link>
  );
}
