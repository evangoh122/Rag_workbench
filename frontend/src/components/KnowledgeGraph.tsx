import React, { useMemo } from 'react';
import { ReactFlow, Background, Controls, MarkerType } from '@xyflow/react';
import type { Edge, Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { Triple } from '../api/chat';
import GraphAnalytics from './GraphAnalytics';

// One node/edge selection bubbled up so the parent can fetch + show evidence.
export interface GraphSelection {
  label: string;
  chunk_id?: string;
  source_file?: string;
  source_loc?: string;
  subject?: string;
  predicate?: string;
  object?: string;
}

interface KnowledgeGraphProps {
  triples: Triple[];
  onSelect?: (sel: GraphSelection) => void;
}

// Node fill by Evidence-Graph node type (Phase C). Falls back to neutral for
// legacy/untyped triples.
const TYPE_COLORS: Record<string, string> = {
  Company: '#1D4ED8',
  Segment: '#0891b2',
  Risk: '#dc2626',
  Executive: '#d97706',
  Metric: '#7c3aed',
  XBRL: '#059669',
  Product: '#db2777',
  Geography: '#4b5563',
};
const DEFAULT_NODE = '#1A1A1A';

const KnowledgeGraph: React.FC<KnowledgeGraphProps> = ({ triples, onSelect }) => {
  const { nodes, edges } = useMemo(() => {
    const nodeMap = new Map<string, Node>();
    const graphEdges: Edge[] = [];

    // Per-node: its type and a representative source chunk (first triple that
    // touches it) so a node click can open evidence too.
    const nodeType = new Map<string, string>();
    const nodeSource = new Map<string, { chunk_id?: string; source_file?: string; source_loc?: string }>();

    const entities = new Set<string>();
    triples.forEach((t) => {
      entities.add(t.subject);
      entities.add(t.object);
      if (t.subject_type) nodeType.set(t.subject, t.subject_type);
      if (t.object_type) nodeType.set(t.object, t.object_type);
      if (!nodeSource.has(t.subject)) {
        nodeSource.set(t.subject, { chunk_id: t.chunk_id, source_file: t.source_file, source_loc: t.source_loc });
      }
      if (!nodeSource.has(t.object)) {
        nodeSource.set(t.object, { chunk_id: t.chunk_id, source_file: t.source_file, source_loc: t.source_loc });
      }
    });

    const entityArray = Array.from(entities);
    const radius = Math.max(200, entityArray.length * 40);

    entityArray.forEach((entity, i) => {
      const angle = (i / entityArray.length) * 2 * Math.PI;
      const x = 400 + radius * Math.cos(angle);
      const y = 300 + radius * Math.sin(angle);
      const type = nodeType.get(entity);
      const bg = (type && TYPE_COLORS[type]) || DEFAULT_NODE;

      nodeMap.set(entity, {
        id: entity,
        data: { label: entity, type, ...nodeSource.get(entity) },
        position: { x, y },
        style: {
          background: bg,
          color: '#FFFFFF',
          border: '1px solid rgba(255, 255, 255, 0.2)',
          borderRadius: '12px',
          padding: '10px 16px',
          fontSize: '12px',
          fontWeight: 600,
          width: 'auto',
          minWidth: '120px',
          textAlign: 'center',
          cursor: 'pointer',
        },
      });
    });

    triples.forEach((t, i) => {
      graphEdges.push({
        id: `e-${i}`,
        source: t.subject,
        target: t.object,
        label: t.predicate,
        data: {
          chunk_id: t.chunk_id,
          source_file: t.source_file,
          source_loc: t.source_loc,
          subject: t.subject,
          predicate: t.predicate,
          object: t.object,
        },
        labelStyle: { fill: '#888888', fontSize: 10, fontWeight: 500, cursor: 'pointer' },
        labelBgStyle: { fill: '#141414', fillOpacity: 0.8 },
        labelBgPadding: [4, 2],
        labelBgBorderRadius: 4,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#4ADE80' },
        style: { stroke: '#4ADE80', strokeWidth: 2 },
      });
    });

    return { nodes: Array.from(nodeMap.values()), edges: graphEdges };
  }, [triples]);

  const handleNodeClick = (_: React.MouseEvent, node: Node) => {
    if (!onSelect) return;
    const d = node.data as Record<string, unknown>;
    onSelect({
      label: String(d.label ?? node.id),
      chunk_id: d.chunk_id as string | undefined,
      source_file: d.source_file as string | undefined,
      source_loc: d.source_loc as string | undefined,
    });
  };

  const handleEdgeClick = (_: React.MouseEvent, edge: Edge) => {
    if (!onSelect) return;
    const d = (edge.data ?? {}) as Record<string, unknown>;
    onSelect({
      label: `${d.subject} → ${d.predicate} → ${d.object}`,
      chunk_id: d.chunk_id as string | undefined,
      source_file: d.source_file as string | undefined,
      source_loc: d.source_loc as string | undefined,
      subject: d.subject as string | undefined,
      predicate: d.predicate as string | undefined,
      object: d.object as string | undefined,
    });
  };

  return (
    <div style={{ width: '100%', height: '100%' }} className="relative bg-background">
      <GraphAnalytics />
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        nodesDraggable={true}
        nodesConnectable={false}
        elementsSelectable={true}
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
      >
        <Background color="rgba(255,255,255,0.05)" gap={20} size={1} />
        <Controls className="[&>button]:bg-surface-elevated [&>button]:border-border [&>button]:text-secondary [&>button]:fill-secondary" />
      </ReactFlow>
    </div>
  );
};

export default KnowledgeGraph;
