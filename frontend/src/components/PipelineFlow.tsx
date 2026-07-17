import React, { useMemo } from 'react';
import { ReactFlow, Background, Controls } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

interface PipelineFlowProps {
  status?: {
    input?: 'success' | 'error' | 'pending';
    retrieval?: 'success' | 'error' | 'pending';
    extraction?: 'success' | 'error' | 'pending';
    math?: 'success' | 'error' | 'pending';
    verification?: 'success' | 'error' | 'pending';
    output?: 'success' | 'error' | 'pending';
  };
}

const PipelineFlow: React.FC<PipelineFlowProps> = ({ status = {} }) => {
  const getNodeStyle = (nodeStatus?: string) => {
    const baseStyle = { 
      borderRadius: '12px', 
      padding: '14px 20px',
      fontSize: '14px',
      fontWeight: 600,
      color: 'white',
      border: '1px solid rgba(255,255,255,0.08)',
      boxShadow: 'none',
      width: 180,
      textAlign: 'center' as const
    };

    switch (nodeStatus) {
      case 'success':
        return { ...baseStyle, background: 'linear-gradient(135deg, #2E8B57 0%, #4ADE80 100%)', borderColor: 'rgba(74, 222, 128, 0.2)' };
      case 'error':
        return { ...baseStyle, background: 'linear-gradient(135deg, #CD5C5C 0%, #F87171 100%)', borderColor: 'rgba(248, 113, 113, 0.2)' };
      case 'pending':
        return { ...baseStyle, background: 'linear-gradient(135deg, var(--color-accent-fill) 0%, var(--color-accent-bright) 100%)', color: 'var(--color-accent-ink)', borderColor: 'var(--color-accent)', animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' };
      default:
        return { ...baseStyle, background: '#1A1A1A', color: '#888888', borderColor: 'rgba(255,255,255,0.08)' };
    }
  };

  const initialNodes = useMemo(() => [
    {
      id: 'input',
      data: { label: '1. User Input' },
      position: { x: 250, y: 50 },
      style: getNodeStyle(status.input),
    },
    {
      id: 'retrieval',
      data: { label: '2. Document Retrieval' },
      position: { x: 250, y: 150 },
      style: getNodeStyle(status.retrieval),
    },
    {
      id: 'extraction',
      data: { label: '3. XBRL Extraction' },
      position: { x: 250, y: 250 },
      style: getNodeStyle(status.extraction),
    },
    {
      id: 'math',
      data: { label: '4. Math Execution' },
      position: { x: 250, y: 350 },
      style: getNodeStyle(status.math),
    },
    {
      id: 'verification',
      data: { label: '5. Verification' },
      position: { x: 250, y: 450 },
      style: getNodeStyle(status.verification),
    },
    {
      id: 'output',
      data: { label: '6. Final Output' },
      position: { x: 250, y: 550 },
      style: getNodeStyle(status.output),
    },
  ], [status]);

  const initialEdges = useMemo(() => [
    { id: 'e1-2', source: 'input', target: 'retrieval', animated: status.retrieval === 'pending', style: { stroke: '#4b5563', strokeWidth: 2 } },
    { id: 'e2-3', source: 'retrieval', target: 'extraction', animated: status.extraction === 'pending', style: { stroke: '#4b5563', strokeWidth: 2 } },
    { id: 'e3-4', source: 'extraction', target: 'math', animated: status.math === 'pending', style: { stroke: '#4b5563', strokeWidth: 2 } },
    { id: 'e4-5', source: 'math', target: 'verification', animated: status.verification === 'pending', style: { stroke: '#4b5563', strokeWidth: 2 } },
    { id: 'e5-6', source: 'verification', target: 'output', animated: status.output === 'pending', style: { stroke: '#4b5563', strokeWidth: 2 } },
  ], [status]);

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={initialNodes}
        edges={initialEdges}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        nodesDraggable={true}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background color="rgba(255,255,255,0.05)" gap={24} size={1} />
        <Controls className="[&>button]:bg-surface-elevated [&>button]:border-border [&>button]:text-secondary [&>button]:fill-secondary" />
      </ReactFlow>
    </div>
  );
};

export default PipelineFlow;

