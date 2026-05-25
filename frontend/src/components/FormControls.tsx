import type { InputHTMLAttributes, TextareaHTMLAttributes, SelectHTMLAttributes, PropsWithChildren } from 'react';

type FieldProps = PropsWithChildren<{
  label: string;
  hint?: string;
  required?: boolean;
  className?: string;
}>;

export function Field({ label, hint, required, children, className = '' }: FieldProps) {
  return (
    <label className={['field', className].filter(Boolean).join(' ')}>
      <span className="field__label">
        {label}{required ? ' *' : ''}
      </span>
      {children}
      {hint ? <span className="field__hint">{hint}</span> : null}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className="input" {...props} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className="textarea" {...props} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className="input" {...props} />;
}
