import React, { useMemo, useRef, useState, useEffect, useCallback } from 'react';
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
  maxNodes?: number;  // Limit nodes for performance
}

// Node fill by Evidence-Graph node type (Phase C).
const TYPE_COLORS: Record<string, string> = {
  Company: '#1D4ED8',
  Segment: '#0891b2',
  Risk: '#dc2626',
  Executive: '#d97706',
  Metric: 'var(--color-accent-fill)',
  XBRL: '#059669',
  Product: '#db2777',
  Geography: '#4b5563',
};
const DEFAULT_NODE = '#1A1A1A';

const KnowledgeGraph: React.FC<KnowledgeGraphProps> = ({ triples, onSelect, maxNodes = 200 }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });

  // Measure container on mount + resize.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(new Set());

  // Reset expanded nodes when the source triples change (e.g. changing company filter)
  useEffect(() => {
    setExpandedNodeIds(new Set());
  }, [triples]);

  const { nodes, edges, truncated } = useMemo(() => {
    const nodeMap = new Map<string, Node>();
    const graphEdges: Edge[] = [];

    const nodeType = new Map<string, string>();
    const nodeSource = new Map<string, { chunk_id?: string; source_file?: string; source_loc?: string }>();

    // Count connections for each entity to prioritize important nodes
    const connectionCount = new Map<string, number>();
    triples.forEach((t) => {
      connectionCount.set(t.subject, (connectionCount.get(t.subject) || 0) + 1);
      connectionCount.set(t.object, (connectionCount.get(t.object) || 0) + 1);
      if (t.subject_type) nodeType.set(t.subject, t.subject_type);
      if (t.object_type) nodeType.set(t.object, t.object_type);
      if (!nodeSource.has(t.subject)) {
        nodeSource.set(t.subject, { chunk_id: t.chunk_id, source_file: t.source_file, source_loc: t.source_loc });
      }
      if (!nodeSource.has(t.object)) {
        nodeSource.set(t.object, { chunk_id: t.chunk_id, source_file: t.source_file, source_loc: t.source_loc });
      }
    });

    // Sort entities by connection count (most connected first)
    const entities = Array.from(connectionCount.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([entity]) => entity);
    
    const totalNodes = entities.length;
    
    // Seed nodes: limit initial set to maxNodes (e.g. 35) for legibility and speed.
    const seedNodes = entities.slice(0, maxNodes);
    
    // Gather all entities that should be displayed
    const displayEntitiesSet = new Set<string>(seedNodes);
    
    // Expand to include immediate neighbors of expanded nodes
    triples.forEach((t) => {
      if (expandedNodeIds.has(t.subject)) {
        displayEntitiesSet.add(t.object);
      }
      if (expandedNodeIds.has(t.object)) {
        displayEntitiesSet.add(t.subject);
      }
    });
    
    const displayEntities = Array.from(displayEntitiesSet);
    const truncated = totalNodes > displayEntities.length;

    // Responsive center and radius - use force-directed-like spacing
    const cx = size.w / 2;
    const cy = size.h / 2;
    const minDim = Math.min(size.w, size.h);
    // Scale radius based on node count for better distribution
    const radius = Math.max(80, Math.min(minDim * 0.4, Math.sqrt(displayEntities.length) * 45));

    displayEntities.forEach((entity, i) => {
      // Use golden angle for better distribution (avoids overlap)
      const angle = i * 2.399963; // golden angle in radians
      const r = radius * Math.sqrt(i / displayEntities.length);
      const x = cx + r * Math.cos(angle);
      const y = cy + r * Math.sin(angle);
      const type = nodeType.get(entity);
      const bg = (type && TYPE_COLORS[type]) || DEFAULT_NODE;
      const connections = connectionCount.get(entity) || 0;

      // Determine if there are connections that are hidden
      const displayedConnections = triples.filter(
        (t) => (t.subject === entity && displayEntitiesSet.has(t.object)) ||
               (t.object === entity && displayEntitiesSet.has(t.subject))
      ).length;
      
      const isExpanded = expandedNodeIds.has(entity);
      const hiddenCount = connections - displayedConnections;
      const label = entity + (isExpanded ? ' ▾' : hiddenCount > 0 ? ` (+${hiddenCount})` : '');

      nodeMap.set(entity, {
        id: entity,
        data: { 
          label, 
          type, 
          connections,
          isExpanded,
          ...nodeSource.get(entity) 
        },
        position: { x, y },
        style: {
          background: bg,
          color: type === 'Metric' ? 'var(--color-accent-ink)' : '#FFFFFF',
          border: isExpanded ? '2px solid #10B981' : '1px solid rgba(255, 255, 255, 0.2)',
          boxShadow: isExpanded ? '0 0 10px rgba(16, 185, 129, 0.4)' : 'none',
          borderRadius: '12px',
          padding: '10px 16px',
          fontSize: '12px',
          fontWeight: 600,
          width: 'auto',
          minWidth: '120px',
          textAlign: 'center',
          cursor: 'pointer',
          // Scale node size by connection count
          opacity: Math.max(0.7, Math.min(1, connections / 5)),
        },
      });
    });

    // Only include edges where both nodes are displayed
    triples.forEach((t, i) => {
      if (displayEntitiesSet.has(t.subject) && displayEntitiesSet.has(t.object)) {
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
      }
    });

    return { nodes: Array.from(nodeMap.values()), edges: graphEdges, truncated };
  }, [triples, size, maxNodes, expandedNodeIds]);

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    if (!onSelect) return;
    const d = node.data as Record<string, unknown>;
    onSelect({
      label: String(d.label ?? node.id),
      chunk_id: d.chunk_id as string | undefined,
      source_file: d.source_file as string | undefined,
      source_loc: d.source_loc as string | undefined,
    });
  }, [onSelect]);

  const handleNodeDoubleClick = useCallback((_: React.MouseEvent, node: Node) => {
    setExpandedNodeIds((prev) => {
      const next = new Set(prev);
      if (next.has(node.id)) {
        next.delete(node.id);
      } else {
        next.add(node.id);
      }
      return next;
    });
  }, []);

  const handleEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
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
  }, [onSelect]);

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', minHeight: 300 }} className="relative bg-background">
      <GraphAnalytics />
      
      {/* Helper for large graphs */}
      {truncated && (
        <div className="absolute top-3 left-3 z-20 bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2 text-xs text-emerald-400 max-w-xs">
          Double-click nodes with a <strong>(+N)</strong> indicator to expand hidden connections.
        </div>
      )}
      
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        nodesDraggable={true}
        nodesConnectable={false}
        elementsSelectable={true}
        onNodeClick={handleNodeClick}
        onNodeDoubleClick={handleNodeDoubleClick}
        onEdgeClick={handleEdgeClick}
        panOnDrag
        zoomOnPinch
        zoomOnScroll
        minZoom={0.3}
        maxZoom={2}
      >
        <Background color="rgba(255,255,255,0.05)" gap={20} size={1} />
        <Controls className="[&>button]:bg-surface-elevated [&>button]:border-border [&>button]:text-secondary [&>button]:fill-secondary [&_svg]:w-4 [&_svg]:h-4" />
      </ReactFlow>
    </div>
  );
};

export default KnowledgeGraph;
