import type { ChangeEvent } from 'react';

type UploadBoxProps = {
  files: File[];
  onFilesChange: (files: File[]) => void;
};

const accept = '.pdf,.png,.jpg,.jpeg,.txt,.docx,.xlsx,.xls';

export function UploadBox({ files, onFilesChange }: UploadBoxProps) {
  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.target.files || []);
    onFilesChange(selected);
  }

  return (
    <div className="upload-box">
      <input id="files" type="file" multiple accept={accept} onChange={handleChange} />
      <label htmlFor="files" className="upload-box__drop">
        <span className="upload-box__icon">+</span>
        <strong>Enviar documentos da semana</strong>
        <small>PDF, imagens, TXT, DOCX, Excel .xlsx/.xls</small>
      </label>
      {files.length > 0 ? (
        <div className="upload-box__list">
          {files.map((file) => (
            <span key={`${file.name}-${file.size}`} className="file-chip">
              {file.name}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
