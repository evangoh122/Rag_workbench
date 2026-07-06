import { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import DataTable from './DataTable';
import { parseSegments } from '../utils/markdownTables';

const ALLOWED = [
  'p', 'strong', 'em', 'code', 'pre', 'ul', 'ol', 'li', 'blockquote',
  'h1', 'h2', 'h3', 'h4', 'a', 'br', 'hr',
  // Kept as a fallback in case a table isn't extracted into a segment.
  'table', 'thead', 'tbody', 'tr', 'th', 'td', 'del',
];

/**
 * Render assistant markdown, but promote GFM tables to interactive TanStack
 * tables (sortable, numeric-aware). Non-table prose falls through to
 * ReactMarkdown unchanged.
 */
export default function MarkdownMessage({ content }: { content: string }) {
  const segments = useMemo(() => parseSegments(content), [content]);

  return (
    <>
      {segments.map((seg, i) =>
        seg.type === 'table' ? (
          <DataTable key={`t${i}`} table={seg.table} />
        ) : (
          <ReactMarkdown key={`m${i}`} remarkPlugins={[remarkGfm]} allowedElements={ALLOWED} skipHtml>
            {seg.content}
          </ReactMarkdown>
        ),
      )}
    </>
  );
}
