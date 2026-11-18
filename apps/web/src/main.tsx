import React, { Component, ReactNode, ErrorInfo } from 'react';
import ReactDOM from 'react-dom/client';
import { ClerkProvider } from '@clerk/clerk-react';
import { App } from './App';
import './index.css';

const CLERK_PUBLISHABLE_KEY =
  import.meta.env.VITE_CLERK_PUBLISHABLE_KEY ||
  'pk_test_aHVtYmxlLWduYXQtMzAxNy5jbGVyay5hY2NvdW50cy5kZXYk';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

class RootErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[Syncnode Root Catch]:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          background: '#0b0e11',
          color: '#eaecef',
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'sans-serif',
          padding: '24px'
        }}>
          <div style={{
            background: '#181a20',
            border: '1px solid #2b313a',
            borderRadius: '12px',
            padding: '32px',
            maxWidth: '480px',
            textAlign: 'center'
          }}>
            <h2 style={{ color: '#f0b90b', margin: '0 0 12px 0' }}>NovexTrade Institutional Exchange</h2>
            <p style={{ color: '#848e9c', fontSize: '14px', marginBottom: '20px' }}>
              The interface encountered a temporary runtime state.
            </p>
            <button
              onClick={() => {
                window.location.href = '/';
              }}
              style={{
                background: '#f0b90b',
                color: '#0b0e11',
                border: '1px solid #f0b90b',
                borderRadius: '6px',
                padding: '10px 20px',
                fontWeight: 700,
                cursor: 'pointer'
              }}
            >
              Reload Interface
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RootErrorBoundary>
      <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY} afterSignOutUrl="/">
        <App />
      </ClerkProvider>
    </RootErrorBoundary>
  </React.StrictMode>
);

