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
      border: '1px solid rgba(255,255,255,0.1)',
      boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
      width: 180,
      textAlign: 'center' as const
    };

    switch (nodeStatus) {
      case 'success':
        return { ...baseStyle, background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)', borderColor: '#34d399' };
      case 'error':
        return { ...baseStyle, background: 'linear-gradient(135deg, #dc2626 0%, #ef4444 100%)', borderColor: '#f87171' };
      case 'pending':
        return { ...baseStyle, background: 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)', borderColor: '#818cf8', animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' };
      default:
        return { ...baseStyle, background: '#161b24', color: '#9ca3af', borderColor: '#202532', boxShadow: 'none' };
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
        <Background color="#202532" gap={24} size={2} />
        <Controls style={{ button: { backgroundColor: '#161b24', border: '1px solid #202532', color: '#9ca3af', fill: '#9ca3af' } }} />
      </ReactFlow>
    </div>
  );
};

export default PipelineFlow;

