export interface DataTableColumn<Row> {
  key: keyof Row;
  label: string;
}

interface DataTableProps<Row extends { code: string }> {
  columns: DataTableColumn<Row>[];
  rows: Row[];
}

export function DataTable<Row extends { code: string }>({ columns, rows }: DataTableProps<Row>) {
  return (
    <section className="panel data-table">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={String(column.key)}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.code}>
              {columns.map((column) => (
                <td key={String(column.key)}>{String(row[column.key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
