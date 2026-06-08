import React from 'react';
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
  const getNodeColor = (nodeStatus?: string) => {
    switch (nodeStatus) {
      case 'success':
        return '#10b981'; // green-500
      case 'error':
        return '#ef4444'; // red-500
      case 'pending':
        return '#3b82f6'; // blue-500
      default:
        return '#4b5563'; // gray-600
    }
  };

  const initialNodes = [
    {
      id: 'input',
      data: { label: 'Input' },
      position: { x: 50, y: 50 },
      style: { background: getNodeColor(status.input), color: 'white', borderRadius: '8px', padding: '10px' },
    },
    {
      id: 'retrieval',
      data: { label: 'Retrieval' },
      position: { x: 50, y: 150 },
      style: { background: getNodeColor(status.retrieval), color: 'white', borderRadius: '8px', padding: '10px' },
    },
    {
      id: 'extraction',
      data: { label: 'XBRL Extraction' },
      position: { x: 50, y: 250 },
      style: { background: getNodeColor(status.extraction), color: 'white', borderRadius: '8px', padding: '10px' },
    },
    {
      id: 'math',
      data: { label: 'Math Execution' },
      position: { x: 50, y: 350 },
      style: { background: getNodeColor(status.math), color: 'white', borderRadius: '8px', padding: '10px' },
    },
    {
      id: 'verification',
      data: { label: 'Verification' },
      position: { x: 50, y: 450 },
      style: { background: getNodeColor(status.verification), color: 'white', borderRadius: '8px', padding: '10px' },
    },
    {
      id: 'output',
      data: { label: 'Output' },
      position: { x: 50, y: 550 },
      style: { background: getNodeColor(status.output), color: 'white', borderRadius: '8px', padding: '10px' },
    },
  ];

  const initialEdges = [
    { id: 'e1-2', source: 'input', target: 'retrieval', animated: status.retrieval === 'pending' },
    { id: 'e2-3', source: 'retrieval', target: 'extraction', animated: status.extraction === 'pending' },
    { id: 'e3-4', source: 'extraction', target: 'math', animated: status.math === 'pending' },
    { id: 'e4-5', source: 'math', target: 'verification', animated: status.verification === 'pending' },
    { id: 'e5-6', source: 'verification', target: 'output', animated: status.output === 'pending' },
  ];

  return (
    <div style={{ width: '100%', height: '100%', background: '#111827' }}>
      <ReactFlow
        nodes={initialNodes}
        edges={initialEdges}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background color="#374151" gap={16} />
        <Controls />
      </ReactFlow>
    </div>
  );
};

export default PipelineFlow;
