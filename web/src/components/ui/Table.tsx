interface Column<T> {
  label: string
  render: (row: T) => React.ReactNode
  width?: string
}

interface Props<T> {
  columns: Column<T>[]
  rows: T[]
  keyField: keyof T
  empty?: string
}

export default function Table<T>({ columns, rows, keyField, empty = 'Nenhum registro encontrado.' }: Props<T>) {
  return (
    <div className="rounded-xl border border-navy-800 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-navy-800" style={{ background: '#141920' }}>
            {columns.map((col, i) => (
              <th key={i} className="px-4 py-3 text-left text-xs font-semibold text-navy-400 uppercase tracking-wider" style={{ width: col.width }}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-navy-500 text-sm">
                {empty}
              </td>
            </tr>
          ) : rows.map((row) => (
            <tr key={String(row[keyField])} className="border-b border-navy-900 hover:bg-navy-900 transition-colors">
              {columns.map((col, i) => (
                <td key={i} className="px-4 py-3 text-navy-200">
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
