// Parse GitHub-flavoured markdown tables out of a message so they can be
// rendered with TanStack Table instead of a static <table>. Everything that
// isn't a table stays as a text segment for ReactMarkdown.

export type ColAlign = 'left' | 'right' | 'center';

export interface ParsedTable {
  headers: string[];
  aligns: ColAlign[];
  rows: string[][];
}

export type Segment =
  | { type: 'text'; content: string }
  | { type: 'table'; table: ParsedTable };

const DELIM_CELL = /^:?-{1,}:?$/;

/** Split a `| a | b |` row into trimmed cells, honouring escaped `\|`. */
export function splitCells(line: string): string[] {
  let s = line.trim();
  if (s.startsWith('|')) s = s.slice(1);
  if (s.endsWith('|')) s = s.slice(0, -1);
  const cells: string[] = [];
  let cur = '';
  for (let i = 0; i < s.length; i++) {
    const ch = s[i];
    if (ch === '\\' && s[i + 1] === '|') {
      cur += '|';
      i++;
      continue;
    }
    if (ch === '|') {
      cells.push(cur.trim());
      cur = '';
      continue;
    }
    cur += ch;
  }
  cells.push(cur.trim());
  return cells;
}

function isDelimiterRow(line: string): boolean {
  if (!line.includes('-')) return false;
  const cells = splitCells(line);
  return cells.length > 0 && cells.every((c) => DELIM_CELL.test(c));
}

function alignOf(cell: string): ColAlign {
  const left = cell.startsWith(':');
  const right = cell.endsWith(':');
  if (left && right) return 'center';
  if (right) return 'right';
  return 'left';
}

/**
 * Split content into ordered text/table segments. A table is a line containing
 * `|` immediately followed by a delimiter row (`| :-- | --: |`), then any number
 * of `|`-rows. Anything else is accumulated as text.
 */
export function parseSegments(content: string): Segment[] {
  const lines = content.split('\n');
  const segments: Segment[] = [];
  let text: string[] = [];

  const flushText = () => {
    if (text.length) {
      segments.push({ type: 'text', content: text.join('\n') });
      text = [];
    }
  };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const next = lines[i + 1];
    const looksLikeHeader =
      line.includes('|') && next !== undefined && isDelimiterRow(next) && !isDelimiterRow(line);

    if (looksLikeHeader) {
      const headers = splitCells(line);
      const aligns = splitCells(next).map(alignOf);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].includes('|') && lines[i].trim() !== '') {
        const cells = splitCells(lines[i]);
        // Normalise ragged rows to the header width.
        while (cells.length < headers.length) cells.push('');
        rows.push(cells.slice(0, headers.length));
        i++;
      }
      flushText();
      segments.push({ type: 'table', table: { headers, aligns, rows } });
    } else {
      text.push(line);
      i++;
    }
  }
  flushText();
  return segments;
}

/**
 * Parse a display value like "15.54B", "-9.1%", or "215,938,000,000" into a
 * number for numeric-aware sorting. Returns null when the cell isn't numeric.
 */
export function parseNumericCell(v: string): number | null {
  if (!v) return null;
  const m = v.replace(/,/g, '').match(/^(-?\d*\.?\d+)\s*([bmk])?%?$/i);
  if (!m) return null;
  let n = parseFloat(m[1]);
  if (Number.isNaN(n)) return null;
  switch ((m[2] || '').toLowerCase()) {
    case 'b':
      n *= 1e9;
      break;
    case 'm':
      n *= 1e6;
      break;
    case 'k':
      n *= 1e3;
      break;
  }
  return n;
}
