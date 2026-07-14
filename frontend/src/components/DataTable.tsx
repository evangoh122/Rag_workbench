import { useMemo, useState } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
  type SortingFn,
} from '@tanstack/react-table';
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react';
import type { ParsedTable, ColAlign } from '../utils/markdownTables';
import { parseNumericCell } from '../utils/markdownTables';

type Row = string[];

// Numeric-aware sort: compare as numbers when both cells parse (15.54B, -9.1%,
// 215,938,000,000), otherwise fall back to locale string compare.
const smartSort: SortingFn<Row> = (rowA, rowB, columnId) => {
  const a = String(rowA.getValue(columnId) ?? '');
  const b = String(rowB.getValue(columnId) ?? '');
  const na = parseNumericCell(a);
  const nb = parseNumericCell(b);
  if (na !== null && nb !== null) return na === nb ? 0 : na < nb ? -1 : 1;
  return a.localeCompare(b);
};

function alignClass(align: ColAlign): string {
  if (align === 'right') return 'text-right';
  if (align === 'center') return 'text-center';
  return 'text-left';
}

export default function DataTable({ table }: { table: ParsedTable }) {
  const [sorting, setSorting] = useState<SortingState>([]);

  const columns = useMemo<ColumnDef<Row>[]>(
    () =>
      table.headers.map((header, idx) => ({
        id: `c${idx}`,
        header,
        accessorFn: (row: Row) => row[idx] ?? '',
        sortingFn: smartSort,
        meta: { align: table.aligns[idx] ?? 'left' },
      })),
    [table],
  );

  const instance = useReactTable({
    data: table.rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          {instance.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => {
                const align = (h.column.columnDef.meta as { align?: ColAlign })?.align ?? 'left';
                const sorted = h.column.getIsSorted();
                return (
                  <th
                    key={h.id}
                    className={`${alignClass(align)} data-table-th`}
                    aria-sort={
                      sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : 'none'
                    }
                  >
                    <button
                      type="button"
                      className="data-table-sort-button"
                      onClick={h.column.getToggleSortingHandler()}
                      aria-label={`Sort by ${String(h.column.columnDef.header)}${sorted ? `, currently ${sorted === 'asc' ? 'ascending' : 'descending'}` : ''}`}
                    >
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {sorted === 'asc' ? (
                        <ChevronUp size={12} />
                      ) : sorted === 'desc' ? (
                        <ChevronDown size={12} />
                      ) : (
                        <ChevronsUpDown size={12} className="data-table-sort-idle" />
                      )}
                    </button>
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {instance.getRowModel().rows.map((row) => (
            <tr key={row.id}>
              {row.getVisibleCells().map((cell) => {
                const align = (cell.column.columnDef.meta as { align?: ColAlign })?.align ?? 'left';
                return (
                  <td key={cell.id} className={alignClass(align)}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
