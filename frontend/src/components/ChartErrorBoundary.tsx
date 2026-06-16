import React, { Component, type ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

/**
 * Error boundary specifically for chart components. Prevents chart rendering
 * errors from crashing the entire message bubble.
 */
class ChartErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.warn('Chart rendering failed:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <div className="mt-3 p-3 bg-surface/50 border border-border/50 rounded-lg flex items-center gap-2 text-xs text-secondary">
          <AlertTriangle size={14} className="text-yellow-500 flex-shrink-0" />
          <span>Chart could not be rendered</span>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ChartErrorBoundary;
