import React, { useMemo } from 'react';
import { ReactFlow, Background, Controls, MarkerType } from '@xyflow/react';
import type { Edge, Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

interface Triple {
  subject: string;
  predicate: string;
  object: string;
}

interface KnowledgeGraphProps {
  triples: Triple[];
}

const KnowledgeGraph: React.FC<KnowledgeGraphProps> = ({ triples }) => {
  const { nodes, edges } = useMemo(() => {
    const nodeMap = new Map<string, Node>();
    const graphEdges: Edge[] = [];
    
    // Extract unique entities for nodes
    const entities = new Set<string>();
    triples.forEach((t) => {
      entities.add(t.subject);
      entities.add(t.object);
    });

    const entityArray = Array.from(entities);
    const radius = Math.max(200, entityArray.length * 40);
    
    // Position nodes in a circle
    entityArray.forEach((entity, i) => {
      const angle = (i / entityArray.length) * 2 * Math.PI;
      const x = 400 + radius * Math.cos(angle);
      const y = 300 + radius * Math.sin(angle);

      nodeMap.set(entity, {
        id: entity,
        data: { label: entity },
        position: { x, y },
        style: {
          background: entity === triples[0]?.subject ? '#1D4ED8' : '#1A1A1A',
          color: '#FFFFFF',
          border: '1px solid rgba(255, 255, 255, 0.2)',
          borderRadius: '12px',
          padding: '10px 16px',
          fontSize: '12px',
          fontWeight: 600,
          width: 'auto',
          minWidth: '120px',
          textAlign: 'center',
        },
      });
    });

    // Create edges from triples
    triples.forEach((t, i) => {
      graphEdges.push({
        id: `e-${i}`,
        source: t.subject,
        target: t.object,
        label: t.predicate,
        labelStyle: { fill: '#888888', fontSize: 10, fontWeight: 500 },
        labelBgStyle: { fill: '#141414', fillOpacity: 0.8 },
        labelBgPadding: [4, 2],
        labelBgBorderRadius: 4,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: '#4ADE80',
        },
        style: {
          stroke: '#4ADE80',
          strokeWidth: 2,
        },
      });
    });

    return {
      nodes: Array.from(nodeMap.values()),
      edges: graphEdges,
    };
  }, [triples]);

  return (
    <div style={{ width: '100%', height: '100%' }} className="bg-background">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        nodesDraggable={true}
        nodesConnectable={false}
        elementsSelectable={true}
      >
        <Background color="rgba(255,255,255,0.05)" gap={20} size={1} />
        <Controls className="[&>button]:bg-surface-elevated [&>button]:border-border [&>button]:text-secondary [&>button]:fill-secondary" />
      </ReactFlow>
    </div>
  );
};

export default KnowledgeGraph;
