import React from 'react';

export default class ErrorBoundary extends React.Component {
  state = { hasError: false, error: null };

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('App error:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            minHeight: '100vh',
            background: '#f0f2f5',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 24,
          }}
        >
          <div
            style={{
              background: '#fff',
              padding: 32,
              borderRadius: 12,
              maxWidth: 420,
              boxShadow: '0 4px 24px rgba(0,0,0,0.12)',
            }}
          >
            <h2 style={{ margin: '0 0 12px', color: '#1a1a1a' }}>Something went wrong</h2>
            <p style={{ margin: '0 0 20px', color: '#555' }}>
              The app hit an error. Try refreshing the page or signing in again.
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              style={{
                padding: '10px 20px',
                background: '#667eea',
                color: '#fff',
                border: 'none',
                borderRadius: 8,
                fontSize: 16,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Refresh page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
