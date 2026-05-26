import React, { useState, useEffect } from 'react';
import { TRANSLATIONS } from '../localization';
import type { Language } from '../localization';
import { API_BASE_URL } from '../config';


interface AnalyticsProps {
  sessionId: number;
  language: Language;
  onBackToDashboard: () => void;
}

interface SessionDetails {
  subject: string;
  topic: string;
  class_level: string;
  lesson_objectives: string;
  teaching_method: string;
  language: string;
  created_at: string;
  messages: Array<{
    sender_type: string;
    sender_name: string;
    message_text: string;
  }>;
}

interface PerformanceAnalytics {
  communication_score: number;
  engagement_score: number;
  time_management_score: number;
  question_handling_score: number;
  suggestions: string;
  transcript_summary: string;
}

export const Analytics: React.FC<AnalyticsProps> = ({
  sessionId,
  language,
  onBackToDashboard,
}) => {
  const t = TRANSLATIONS[language];

  // Page States
  const [sessionDetails, setSessionDetails] = useState<SessionDetails | null>(null);
  const [analytics, setAnalytics] = useState<PerformanceAnalytics | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Fetch session details & analytics
  useEffect(() => {
    const fetchAll = async () => {
      try {
        // First end session to generate analytics (or load if already exists)
        const endRes = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/end`, {
          method: 'POST',
        });
        const analyticsData = await endRes.json();
        setAnalytics(analyticsData);

        // Get session details and messages
        const detailsRes = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}`);
        const detailsData = await detailsRes.json();
        setSessionDetails(detailsData);

        setIsLoading(false);
      } catch (err) {
        console.error('Error fetching analytics:', err);
        setIsLoading(false);
      }
    };

    fetchAll();
  }, [sessionId]);

  // A simple markdown helper that formats basic markdown markers (**bold**, *italics*, bullet points) to HTML
  const formatFeedbackText = (text: string) => {
    if (!text) return '';
    
    // Replace **bold** with <strong>bold</strong>
    let html = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Replace *italics* with <em>italics</em>
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    
    // Split into paragraphs / list items
    const lines = html.split('\n');
    return lines.map((line, idx) => {
      const trimmed = line.trim();
      if (trimmed.startsWith('-') || trimmed.startsWith('*')) {
        return <li key={idx} style={{ marginLeft: '1.25rem', marginBottom: '0.4rem' }}>{trimmed.slice(1).trim()}</li>;
      }
      if (trimmed.startsWith('#')) {
        // Headers
        const headerLevel = (trimmed.match(/#/g) || []).length;
        const cleanText = trimmed.replace(/#/g, '').trim();
        if (headerLevel === 1) return <h1 key={idx} style={{ margin: '1rem 0 0.5rem', fontSize: '1.5rem', fontWeight: 700 }}>{cleanText}</h1>;
        if (headerLevel === 2) return <h2 key={idx} style={{ margin: '1rem 0 0.5rem', fontSize: '1.3rem', fontWeight: 700 }}>{cleanText}</h2>;
        return <h3 key={idx} style={{ margin: '1rem 0 0.5rem', fontSize: '1.1rem', fontWeight: 700 }}>{cleanText}</h3>;
      }
      if (trimmed === '') {
        return <div key={idx} style={{ height: '0.5rem' }} />;
      }
      return <p key={idx} style={{ marginBottom: '0.75rem' }}>{line}</p>;
    });
  };

  const downloadReport = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/report`);
      if (res.ok) {
        const data = await res.json();
        const element = document.createElement("a");
        const file = new Blob([data.report_md], { type: 'text/markdown' });
        element.href = URL.createObjectURL(file);
        element.download = `SkillX_Pedagogical_Report_Session_${sessionId}.md`;
        document.body.appendChild(element);
        element.click();
        document.body.removeChild(element);
      } else {
        alert("Failed to download report.");
      }
    } catch (e) {
      console.error(e);
      alert("Error downloading report.");
    }
  };

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '5rem', color: 'var(--text-muted)' }}>
        <h2 className="gradient-text">Analyzing Lesson Delivery...</h2>
        <p style={{ marginTop: '0.5rem' }}>Evaluating transcript, engagement indexes, and lesson coverage.</p>
      </div>
    );
  }

  // Calculate overall performance average
  const averageScore = analytics
    ? Math.round(
        (analytics.communication_score +
          analytics.engagement_score +
          analytics.time_management_score +
          analytics.question_handling_score) /
          4
      )
    : 0;

  return (
    <div className="analytics-container">
      {/* Banner Card */}
      <div className="analytics-banner glass">
        <div>
          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--primary)', textTransform: 'uppercase' }}>
            Micro-Teaching Evaluation Report
          </span>
          <h1 className="gradient-text" style={{ fontSize: '2rem', fontWeight: 700 }}>
            {sessionDetails?.subject}: {sessionDetails?.topic}
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', marginTop: '0.25rem' }}>
            {sessionDetails?.class_level} | Teaching Method: <strong>{sessionDetails?.teaching_method}</strong>
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          <div style={{ textAlign: 'right', marginRight: '1rem' }}>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{t.overallScore}</span>
            <h2 style={{ fontSize: '2.5rem', fontWeight: 800, color: 'var(--color-success)', lineHeight: 1 }}>
              {averageScore}/100
            </h2>
          </div>
          <button
            className="btn-secondary"
            onClick={downloadReport}
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', border: '1px solid var(--border-card)', padding: '0.75rem 1rem', borderRadius: '12px' }}
            id="analytics-btn-download-report"
            type="button"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
            Download Report
          </button>
          <button 
            className="btn-primary" 
            onClick={onBackToDashboard}
            id="analytics-btn-back"
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', padding: '0.75rem 1.25rem' }}
            type="button"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="19" x2="5" y1="12" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
            {t.backBtn}
          </button>
        </div>
      </div>

      {/* Score Cards Grid */}
      {analytics && (
        <div className="metrics-grid">
          {/* Communication Score */}
          <div className="metric-card glass" id="metric-communication">
            <div 
              className="radial-progress" 
              style={{ '--percentage': analytics.communication_score } as React.CSSProperties}
              data-score={analytics.communication_score}
            />
            <span className="metric-title">{t.scoreCommunication}</span>
          </div>

          {/* Engagement Score */}
          <div className="metric-card glass" id="metric-engagement">
            <div 
              className="radial-progress" 
              style={{ '--percentage': analytics.engagement_score } as React.CSSProperties}
              data-score={analytics.engagement_score}
            />
            <span className="metric-title">{t.scoreEngagement}</span>
          </div>

          {/* Time Management Score */}
          <div className="metric-card glass" id="metric-time">
            <div 
              className="radial-progress" 
              style={{ '--percentage': analytics.time_management_score } as React.CSSProperties}
              data-score={analytics.time_management_score}
            />
            <span className="metric-title">{t.scoreTime}</span>
          </div>

          {/* Question Handling Score */}
          <div className="metric-card glass" id="metric-questions">
            <div 
              className="radial-progress" 
              style={{ '--percentage': analytics.question_handling_score } as React.CSSProperties}
              data-score={analytics.question_handling_score}
            />
            <span className="metric-title">{t.scoreQuestion}</span>
          </div>
        </div>
      )}

      {/* Suggestions vs Transcript details */}
      <div className="analytics-details-grid">
        
        {/* Left: Feedback suggestions */}
        <div className="suggestions-card glass">
          <h3 className="gradient-text" style={{ fontSize: '1.25rem', fontWeight: 700 }}>
            {t.suggestionsTitle}
          </h3>
          
          {analytics?.transcript_summary && (
            <div 
              style={{ 
                background: 'rgba(255, 255, 255, 0.03)', 
                padding: '1rem', 
                borderRadius: '8px', 
                marginBottom: '1.5rem',
                borderLeft: '4px solid var(--primary)',
                fontSize: '0.9rem'
              }}
            >
              <strong>{t.transcriptSummaryTitle}:</strong> {analytics.transcript_summary}
            </div>
          )}

          <div className="suggestions-content">
            {analytics ? formatFeedbackText(analytics.suggestions) : ''}
          </div>
        </div>

        {/* Right: Transcript Explorer */}
        <div className="suggestions-card glass" style={{ display: 'flex', flexDirection: 'column', maxHeight: '650px' }}>
          <h3 className="gradient-text" style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            {t.recentTranscript}
          </h3>
          
          <div style={{ flex: 1, overflowY: 'auto', paddingRight: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {sessionDetails?.messages && sessionDetails.messages.map((m, idx) => (
              <div 
                key={idx} 
                style={{ 
                  background: m.sender_type === 'teacher' ? 'rgba(99, 102, 241, 0.1)' : m.sender_type === 'system' ? 'rgba(245, 158, 11, 0.08)' : 'rgba(255, 255, 255, 0.02)',
                  border: `1px solid ${m.sender_type === 'teacher' ? 'rgba(99, 102, 241, 0.2)' : m.sender_type === 'system' ? 'rgba(245, 158, 11, 0.15)' : 'var(--border-card)'}`,
                  padding: '0.75rem',
                  borderRadius: '8px',
                  fontSize: '0.85rem'
                }}
                id={`analytics-msg-${idx}`}
              >
                <div style={{ fontWeight: 700, color: m.sender_type === 'teacher' ? 'var(--primary)' : 'var(--accent-cyan)', marginBottom: '0.15rem', fontSize: '0.75rem' }}>
                  {m.sender_name} ({m.sender_type.toUpperCase()})
                </div>
                <div style={{ color: 'var(--text-primary)' }}>{m.message_text}</div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
};
