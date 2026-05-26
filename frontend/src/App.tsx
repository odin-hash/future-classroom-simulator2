import { useState } from 'react';
import { TRANSLATIONS } from './localization';
import type { Language } from './localization';
import { ThemeToggle } from './components/ThemeToggle';
import { Dashboard } from './pages/Dashboard';
import { Classroom } from './pages/Classroom';
import { Analytics } from './pages/Analytics';
import { API_BASE_URL } from './config';

function App() {
  const [language, setLanguage] = useState<Language>('English');
  const [currentPage, setCurrentPage] = useState<'dashboard' | 'classroom' | 'analytics'>('dashboard');
  const [currentSessionId, setCurrentSessionId] = useState<number | null>(null);
  const [connectionError, setConnectionError] = useState<{
    message: string;
    url: string;
    errorType: string;
  } | null>(null);
  const [lastSessionData, setLastSessionData] = useState<any>(null);

  const t = TRANSLATIONS[language];

  // Callback to start a new classroom simulation
  const handleStartSession = async (sessionData: any) => {
    setLastSessionData(sessionData);
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000); // 10-second timeout

      const response = await fetch(`${API_BASE_URL}/api/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sessionData),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP Error ${response.status}: ${response.statusText || 'Failed to create session'}`);
      }
      
      const data = await response.json();
      if (data.language) {
        setLanguage(data.language as Language);
      }
      setCurrentSessionId(data.id);
      setCurrentPage('classroom');
    } catch (err: any) {
      console.error('Error starting session:', err);
      let errorType = "Network Error / CORS Issue";
      let message = err.message || "Failed to establish contact with the server.";
      
      if (err.name === 'AbortError') {
        errorType = "Connection Timeout";
        message = "The request timed out after 10 seconds. The server might be booting up (cold start) or offline.";
      } else if (err.message && err.message.includes("Failed to fetch")) {
        errorType = "Server Unreachable";
        message = "No response was received. The backend server might be offline, or CORS has blocked the origin.";
      }
      
      setConnectionError({
        message,
        url: `${API_BASE_URL}/api/sessions`,
        errorType
      });
    }
  };

  // Callback to view analytical scorecard of a past session
  const handleSelectPastSession = async (sessionId: number) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}`);
      if (response.ok) {
        const data = await response.json();
        if (data.language) {
          setLanguage(data.language as Language);
        }
      }
    } catch (e) {
      console.warn("Failed to fetch past session language:", e);
    }
    setCurrentSessionId(sessionId);
    setCurrentPage('analytics');
  };

  // Callback to complete session and view scores
  const handleEndSession = (sessionId: number) => {
    console.log("Session completed:", sessionId);
    setCurrentPage('analytics');
  };

  // Callback to exit simulator back to dashboard
  const handleExit = () => {
    if (window.confirm('Are you sure you want to exit the simulation? Active progress will be evaluated.')) {
      setCurrentPage('analytics');
    }
  };

  const handleBackToDashboard = () => {
    setCurrentSessionId(null);
    setCurrentPage('dashboard');
  };

  return (
    <div className="app-container">
      {currentPage === 'classroom' ? (
        currentSessionId !== null && (
          <Classroom
            sessionId={currentSessionId}
            language={language}
            onEndSession={handleEndSession}
            onExit={handleExit}
          />
        )
      ) : (
        <>
          {/* Navbar Header */}
          <header className="navbar">
            <div className="nav-logo" onClick={handleBackToDashboard} style={{ cursor: 'pointer' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-primary)' }}>
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 10 12 5 2 10l10 5 10-5z"/><path d="M6 12v5c0 0 2.5 3 6 3s6-3 6-3v-5"/><line x1="22" y1="10" x2="22" y2="16"/><circle cx="22" cy="16.5" r="0.5" fill="currentColor"/></svg>
              </span>
              <div>
                <h1 style={{ fontSize: '1.25rem', fontWeight: 800, lineHeight: 1.1 }}>
                  {t.title}
                </h1>
                <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 500 }}>
                  {t.subtitle}
                </p>
              </div>
            </div>

            <div className="nav-actions">
              {/* Language selector */}
              <select 
                className="lang-select"
                value={language}
                onChange={(e) => setLanguage(e.target.value as Language)}
                id="nav-lang-select"
              >
                <option value="English">English</option>
                <option value="Hindi">हिंदी (Hindi)</option>
                <option value="Bengali">বাংলা (Bengali)</option>
              </select>

              {/* Theme switcher */}
              <ThemeToggle />
            </div>
          </header>

          {/* Page Routing Container */}
          <main className="main-content">
            {currentPage === 'dashboard' && (
              <Dashboard
                language={language}
                onStartSession={handleStartSession}
                onSelectPastSession={handleSelectPastSession}
              />
            )}

            {currentPage === 'analytics' && currentSessionId !== null && (
              <Analytics
                sessionId={currentSessionId}
                language={language}
                onBackToDashboard={handleBackToDashboard}
              />
            )}
          </main>
        </>
      )}

      {connectionError && (
        <div className="connection-error-overlay" style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          backgroundColor: 'rgba(0,0,0,0.7)',
          backdropFilter: 'blur(8px)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 10000,
          padding: '20px'
        }}>
          <div className="connection-error-card" style={{
            background: 'rgba(30, 30, 40, 0.95)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '12px',
            padding: '24px',
            maxWidth: '500px',
            width: '100%',
            boxShadow: '0 20px 40px rgba(0,0,0,0.5)',
            color: '#ffffff'
          }}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '1.25rem', color: '#ff4a4a', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              Backend Connection Failed
            </h3>
            <p style={{ fontSize: '0.9rem', color: '#cccccc', margin: '0 0 16px 0', lineHeight: 1.5 }}>
              Could not initiate classroom simulation. The frontend could not establish a connection to the Python backend server.
            </p>
            
            <div style={{ background: 'rgba(0,0,0,0.3)', padding: '12px', borderRadius: '6px', fontSize: '0.8rem', margin: '0 0 20px 0', fontFamily: 'monospace', border: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ marginBottom: '6px' }}><strong style={{ color: '#ffc107' }}>API URL:</strong> {connectionError.url}</div>
              <div style={{ marginBottom: '6px' }}><strong style={{ color: '#ffc107' }}>Error Type:</strong> {connectionError.errorType}</div>
              <div><strong style={{ color: '#ffc107' }}>Message:</strong> {connectionError.message}</div>
            </div>
            
            <h4 style={{ margin: '0 0 8px 0', fontSize: '0.85rem', fontWeight: 600 }}>Troubleshooting Steps:</h4>
            <ul style={{ fontSize: '0.8rem', margin: '0 0 20px 0', paddingLeft: '18px', color: '#cccccc', lineHeight: 1.4 }}>
              <li>Verify that the Python backend server is running and accessible.</li>
              <li>Check if the environment variable <code>VITE_API_URL</code> is correctly configured in your <code>.env.production</code>.</li>
              <li>Confirm the FastAPI server's CORS settings allow requests from this origin.</li>
              <li>If hosted on Render/Railway, the server may be waking up from a sleep state (cold start). Try again in a minute.</li>
            </ul>
            
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button 
                onClick={() => setConnectionError(null)}
                style={{
                  background: 'rgba(255,255,255,0.1)',
                  color: 'white',
                  border: 'none',
                  padding: '8px 16px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '0.85rem'
                }}
              >
                Dismiss
              </button>
              <button 
                onClick={() => {
                  setConnectionError(null);
                  handleStartSession(lastSessionData);
                }}
                style={{
                  background: 'var(--primary, #007acc)',
                  color: 'white',
                  border: 'none',
                  padding: '8px 16px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  fontWeight: 600
                }}
              >
                Retry Connection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
