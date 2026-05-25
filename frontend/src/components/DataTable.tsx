type DataTableProps = {
  rows: Record<string, unknown>[];
  emptyText?: string;
};

function renderValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Sim' : 'Não';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function DataTable({ rows, emptyText = 'Nenhum registro encontrado.' }: DataTableProps) {
  if (!rows.length) return <div className="empty-state compact">{emptyText}</div>;

  const columns = Object.keys(rows[0]).slice(0, 8);

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column.replaceAll('_', ' ')}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={String(row.id ?? index)}>
              {columns.map((column) => <td key={column}>{renderValue(row[column])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
