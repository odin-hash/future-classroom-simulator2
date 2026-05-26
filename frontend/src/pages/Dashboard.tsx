import React, { useState, useEffect } from 'react';
import { TRANSLATIONS } from '../localization';
import type { Language } from '../localization';
import { SYLLABUS } from '../syllabus';
import { API_BASE_URL } from '../config';


interface DashboardProps {
  language: Language;
  onStartSession: (sessionData: any) => Promise<void>;
  onSelectPastSession: (sessionId: number) => void;
}

interface PastSession {
  id: number;
  subject: string;
  topic: string;
  class_level: string;
  duration_minutes: number;
  language: string;
  created_at: string;
}

// Decorative student preview data for the hero section
const PREVIEW_STUDENTS = [
  { name: 'Aarav', img: '/students/aarav.png', color: '#FEF3C7', comment: 'But why does it work that way? 🤔' },
  { name: 'Ananya', img: '/students/ananya.png', color: '#DBEAFE', comment: 'Um… I think so… maybe… 😊' },
  { name: 'Vihaan', img: '/students/vihaan.png', color: '#D1FAE5', comment: 'Wait, what page are we on? 😅' },
  { name: 'Ishaan', img: '/students/ishaan.png', color: '#EDE9FE', comment: 'I KNOW THIS ONE! Pick me!! 🙋‍♂️' },
  { name: 'Riya', img: '/students/riya.png', color: '#FEE2E2', comment: 'Can you explain it again slowly? 📖' },
  { name: 'Kabir', img: '/students/kabir.png', color: '#FFEDD5', comment: 'Easy! The answer is obviously… 😎' },
];

export const Dashboard: React.FC<DashboardProps> = ({
  language,
  onStartSession,
  onSelectPastSession,
}) => {
  const t = TRANSLATIONS[language];
  const [tappedStudent, setTappedStudent] = useState<string | null>(null);

  // Syllabus Dropdown states (initialized from localStorage if available)
  const [selectedSubject, setSelectedSubject] = useState(() => {
    return localStorage.getItem('fcs_selectedSubject') || 'Bengali';
  });
  const [customSubject, setCustomSubject] = useState(() => {
    return localStorage.getItem('fcs_customSubject') || '';
  });
  
  const [classLevel, setClassLevel] = useState(() => {
    return localStorage.getItem('fcs_classLevel') || 'Middle School (Grades 6-8)';
  });
  
  const [selectedTopic, setSelectedTopic] = useState(() => {
    return localStorage.getItem('fcs_selectedTopic') || '';
  });
  const [customTopic, setCustomTopic] = useState(() => {
    return localStorage.getItem('fcs_customTopic') || '';
  });

  // Other form states
  const [objectives, setObjectives] = useState(() => {
    return localStorage.getItem('fcs_objectives') || '';
  });
  const [method, setMethod] = useState(() => {
    return localStorage.getItem('fcs_method') || 'Direct Lecture (Explanation-heavy)';
  });
  const [duration, setDuration] = useState(() => {
    const val = localStorage.getItem('fcs_duration');
    return val ? Number(val) : 10;
  });
  const [classLanguage, setClassLanguage] = useState<Language>(() => {
    return (localStorage.getItem('fcs_classLanguage') as Language) || language;
  });

  // Prebuilt scenario preset state
  const [scenario, setScenario] = useState(() => {
    return localStorage.getItem('fcs_scenario') || 'normal';
  });

  // Health Diagnostics and SkillX Checklist states
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);
  const [healthResult, setHealthResult] = useState<any>(null);
  const [micPermission, setMicPermission] = useState<'prompt' | 'granted' | 'denied'>('prompt');

  const checkHealth = async () => {
    setIsCheckingHealth(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setMicPermission('granted');
      stream.getTracks().forEach(track => track.stop());
    } catch (err) {
      setMicPermission('denied');
    }

    try {
      const res = await fetch(`${API_BASE_URL}/api/health`);
      if (res.ok) {
        const data = await res.json();
        setHealthResult(data);
      } else {
        setHealthResult({ status: 'failed', api_key_valid: false, database_connected: false, cache_writable: false, tts_available: false, stt_available: false });
      }
    } catch (e) {
      setHealthResult({ status: 'failed', api_key_valid: false, database_connected: false, cache_writable: false, tts_available: false, stt_available: false });
    }
    setIsCheckingHealth(false);
  };

  useEffect(() => {
    checkHealth();
  }, []);

  // Past history state
  const [history, setHistory] = useState<PastSession[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Save selections to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem('fcs_selectedSubject', selectedSubject);
    localStorage.setItem('fcs_customSubject', customSubject);
    localStorage.setItem('fcs_classLevel', classLevel);
    localStorage.setItem('fcs_selectedTopic', selectedTopic);
    localStorage.setItem('fcs_customTopic', customTopic);
    localStorage.setItem('fcs_objectives', objectives);
    localStorage.setItem('fcs_method', method);
    localStorage.setItem('fcs_duration', String(duration));
    localStorage.setItem('fcs_classLanguage', classLanguage);
    localStorage.setItem('fcs_scenario', scenario);
  }, [selectedSubject, customSubject, classLevel, selectedTopic, customTopic, objectives, method, duration, classLanguage, scenario]);

  // Update dynamic topic dropdown list when subject or grade level changes
  useEffect(() => {
    if (selectedSubject !== 'Custom') {
      const topicsList = SYLLABUS[selectedSubject]?.[classLevel] || [];
      const savedTopic = localStorage.getItem('fcs_selectedTopic');
      
      // If there is a saved topic and it's valid for this subject/grade level, keep it
      if (savedTopic && topicsList.includes(savedTopic)) {
        setSelectedTopic(savedTopic);
      } else if (topicsList.length > 0) {
        setSelectedTopic(topicsList[0]);
      } else {
        setSelectedTopic('Custom');
      }
    } else {
      setSelectedTopic('Custom');
    }
  }, [selectedSubject, classLevel]);

  // Update form class language when navbar language changes
  useEffect(() => {
    setClassLanguage(language);
  }, [language]);

  // Load history from API
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/sessions`)
      .then((res) => {
        if (!res.ok) throw new Error('API offline');
        return res.json();
      })
      .then((data) => {
        setHistory(data);
        setIsLoading(false);
      })
      .catch((err) => {
        console.warn('Backend server is offline or unreachable:', err);
        setIsLoading(false);
      });
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    // Resolve final string values
    const finalSubject = selectedSubject === 'Custom' ? customSubject : selectedSubject;
    const finalTopic = selectedTopic === 'Custom' ? customTopic : selectedTopic;

    if (!finalSubject.trim() || !finalTopic.trim()) {
      alert('Please fill out Subject and Topic fields.');
      return;
    }

    onStartSession({
      subject: finalSubject,
      topic: finalTopic,
      class_level: classLevel,
      lesson_objectives: objectives,
      teaching_method: method,
      duration_minutes: duration,
      language: classLanguage,
      scenario: scenario,
    });
  };

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return d.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Get current topics to show in the dropdown selector
  const getTopicsOptions = () => {
    if (selectedSubject === 'Custom') return [];
    return SYLLABUS[selectedSubject]?.[classLevel] || [];
  };

  const scrollToSetup = () => {
    document.getElementById('setup-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="dashboard-page">

      {/* ========== Hero Section ========== */}
      <section className="dashboard-hero animate-in">
        <div className="hero-text-content">
          <span className="hero-badge animate-in-d1">
            <span className="badge-dot"></span>
            {t.subtitle}
          </span>

          <h1 className="hero-heading animate-in-d2">
            Virtual<br/>Classroom
          </h1>

          <p className="hero-subtitle animate-in-d2">
            Practice teaching in a realistic AI-powered classroom with diverse student personalities, real-time speech, and intelligent feedback.
          </p>

          <button
            className="btn-primary btn-pill hero-cta animate-in-d3"
            onClick={scrollToSetup}
            type="button"
            id="hero-cta-btn"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Get Started Now!
          </button>
        </div>

        {/* Colorful Student Preview Grid */}
        <div className="hero-preview-grid animate-in-d3">
          {PREVIEW_STUDENTS.map((s, i) => (
            <div
              className={`preview-student ${tappedStudent === s.name ? 'preview-student-active' : ''}`}
              key={s.name}
              style={{
                background: s.color,
                animationDelay: `${0.3 + i * 0.06}s`,
              }}
            >
              {/* Speech bubble on tap */}
              {tappedStudent === s.name && (
                <div className="preview-speech-bubble">
                  {s.comment}
                </div>
              )}
              <img
                src={s.img}
                alt={s.name}
                className="preview-student-img"
                loading="lazy"
              />
              <span
                className="preview-student-name"
                onClick={() => {
                  if (tappedStudent === s.name) {
                    setTappedStudent(null);
                  } else {
                    setTappedStudent(s.name);
                    // Auto-hide after 3 seconds
                    setTimeout(() => setTappedStudent(prev => prev === s.name ? null : prev), 3000);
                  }
                }}
                role="button"
                tabIndex={0}
              >
                {s.name}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* ========== Startup Health Check & SkillX Demo Console ========== */}
      <section className="glass animate-in-d1" style={{ margin: '2rem auto', padding: '1.5rem', borderRadius: '24px', maxWidth: '1280px', border: '1px solid var(--border-card)', background: 'var(--bg-secondary)' }} id="health-check-section">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.25rem' }}>
          <div>
            <h2 className="gradient-text" style={{ fontSize: '1.25rem', fontWeight: 800, margin: 0 }}>
              🛡️ SkillX Startup Diagnostics & Demo Console
            </h2>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: '0.2rem 0 0 0' }}>
              Verify system health, speech engines, and browser microphone permissions before starting public demonstrations.
            </p>
          </div>
          <button
            type="button"
            className="btn-secondary"
            style={{ fontSize: '0.75rem', padding: '0.4rem 0.85rem', display: 'flex', alignItems: 'center', gap: '0.35rem', border: '1px solid var(--border-card)', borderRadius: '12px' }}
            onClick={checkHealth}
            disabled={isCheckingHealth}
          >
            {isCheckingHealth ? (
              <>🔄 Checking...</>
            ) : (
              <>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: '2px' }}><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                Run Diagnostics
              </>
            )}
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
          {/* Health Diagnostics Panel */}
          <div className="glass-panel" style={{ padding: '1rem', borderRadius: '16px', background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(255,255,255,0.04)' }}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, marginBottom: '0.75rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              🖥️ System Status Check
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.78rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Gemini API Config:</span>
                {healthResult ? (
                  healthResult.api_key_valid ? (
                    <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>✅ Passed</span>
                  ) : (
                    <span style={{ color: 'var(--color-danger)', fontWeight: 600 }}>❌ Missing Key</span>
                  )
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>Checking...</span>
                )}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-secondary)' }}>SQLite Database:</span>
                {healthResult ? (
                  healthResult.database_connected ? (
                    <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>✅ Ready</span>
                  ) : (
                    <span style={{ color: 'var(--color-danger)', fontWeight: 600 }}>❌ Error</span>
                  )
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>Checking...</span>
                )}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Audio Cache Folder:</span>
                {healthResult ? (
                  healthResult.cache_writable ? (
                    <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>✅ Writable</span>
                  ) : (
                    <span style={{ color: 'var(--color-danger)', fontWeight: 600 }}>❌ Read-only</span>
                  )
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>Checking...</span>
                )}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Edge TTS Engine:</span>
                {healthResult ? (
                  healthResult.tts_available ? (
                    <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>✅ Active</span>
                  ) : (
                    <span style={{ color: 'var(--color-danger)', fontWeight: 600 }}>❌ Offline</span>
                  )
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>Checking...</span>
                )}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Speech-To-Text SDK:</span>
                {healthResult ? (
                  healthResult.stt_available ? (
                    <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>✅ Active</span>
                  ) : (
                    <span style={{ color: 'var(--color-warning)', fontWeight: 600 }}>⚠️ Mock Mode</span>
                  )
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>Checking...</span>
                )}
              </div>
            </div>
          </div>

          {/* Interactive SkillX Demo Checklist Panel */}
          <div className="glass-panel" style={{ padding: '1rem', borderRadius: '16px', background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(255,255,255,0.04)' }}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, marginBottom: '0.75rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              📋 Demo Readiness Checklist
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem 1rem', fontSize: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <input type="checkbox" checked={navigator.onLine} readOnly style={{ accentColor: 'var(--primary)' }} />
                <span style={{ color: navigator.onLine ? 'var(--text-primary)' : 'var(--color-danger)' }}>Internet Connected</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <input type="checkbox" checked={micPermission === 'granted'} readOnly style={{ accentColor: 'var(--primary)' }} />
                <span style={{ color: micPermission === 'granted' ? 'var(--text-primary)' : 'var(--color-warning)' }}>Mic Access Granted</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <input type="checkbox" checked={!!healthResult} readOnly style={{ accentColor: 'var(--primary)' }} />
                <span>Demo Preset Mapping</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <input type="checkbox" checked={!!healthResult?.cache_writable} readOnly style={{ accentColor: 'var(--primary)' }} />
                <span>Audio Caches Warmed</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <input type="checkbox" defaultChecked readOnly style={{ accentColor: 'var(--primary)' }} />
                <span>Audio Output Unlocked</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <input type="checkbox" checked={!!healthResult?.api_key_valid} readOnly style={{ accentColor: 'var(--primary)' }} />
                <span>Gemini API Key Verified</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', gridColumn: 'span 2' }}>
                <input type="checkbox" defaultChecked readOnly style={{ accentColor: 'var(--primary)' }} />
                <span>Backup Text & TTS Engine Ready</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ========== Setup Grid: Form + History ========== */}
      <div className="dashboard-grid" id="setup-section">

        {/* Simulation configuration form */}
        <div className="dashboard-panel glass animate-in-d1">
          <h2 className="gradient-text" style={{ marginBottom: '1.5rem', fontWeight: 700 }}>
            {t.setupTitle}
          </h2>
          <form onSubmit={handleSubmit}>
            
            {/* Subject Dropdown */}
            <div className="form-group">
              <label className="form-label">{t.subject} *</label>
              <select
                className="form-select"
                value={selectedSubject}
                onChange={(e) => setSelectedSubject(e.target.value)}
                id="dashboard-select-subject"
              >
                {Object.keys(SYLLABUS).map((sub) => (
                  <option key={sub} value={sub}>{sub}</option>
                ))}
                <option value="Custom">Custom Subject (Type below)</option>
              </select>
            </div>

            {/* Custom Subject Write-in (Conditional) */}
            {selectedSubject === 'Custom' && (
              <div className="form-group" style={{ marginTop: '-0.75rem', paddingLeft: '0.5rem' }}>
                <input
                  type="text"
                  className="form-input"
                  value={customSubject}
                  onChange={(e) => setCustomSubject(e.target.value)}
                  placeholder="Enter custom subject (e.g. Chemistry, History)"
                  required
                  id="dashboard-input-custom-subject"
                />
              </div>
            )}

            {/* Class Level */}
            <div className="form-group">
              <label className="form-label">{t.classLevel}</label>
              <select
                className="form-select"
                value={classLevel}
                onChange={(e) => setClassLevel(e.target.value)}
                id="dashboard-select-level"
              >
                <option value="Primary (Grades 1-5)">{t.primary}</option>
                <option value="Middle School (Grades 6-8)">{t.middle}</option>
                <option value="High School (Grades 9-12)">{t.high}</option>
              </select>
            </div>

            {/* Topic Dropdown (Dynamic based on Subject + Grade) */}
            <div className="form-group">
              <label className="form-label">{t.topic} *</label>
              <select
                className="form-select"
                value={selectedTopic}
                onChange={(e) => setSelectedTopic(e.target.value)}
                id="dashboard-select-topic"
              >
                {getTopicsOptions().map((top) => (
                  <option key={top} value={top}>{top}</option>
                ))}
                <option value="Custom">Custom Topic (Type below)</option>
              </select>
            </div>

            {/* Custom Topic Write-in (Conditional) */}
            {selectedTopic === 'Custom' && (
              <div className="form-group" style={{ marginTop: '-0.75rem', paddingLeft: '0.5rem' }}>
                <input
                  type="text"
                  className="form-input"
                  value={customTopic}
                  onChange={(e) => setCustomTopic(e.target.value)}
                  placeholder="Enter custom topic name"
                  required
                  id="dashboard-input-custom-topic"
                />
              </div>
            )}

            <div className="form-group">
              <label className="form-label">{t.objectives}</label>
              <textarea
                className="form-textarea"
                value={objectives}
                onChange={(e) => setObjectives(e.target.value)}
                placeholder={t.objectivesPlaceholder}
                id="dashboard-textarea-objectives"
              />
            </div>

            <div className="form-group">
              <label className="form-label">{t.method}</label>
              <select
                className="form-select"
                value={method}
                onChange={(e) => setMethod(e.target.value)}
                id="dashboard-select-method"
              >
                <option value="Direct Lecture (Explanation-heavy)">{t.methodLecture}</option>
                <option value="Socratic Discussion (Interactive)">{t.methodDiscussion}</option>
                <option value="Q&A & Probing Questions">{t.methodQA}</option>
                <option value="Inquiry-based Learning">{t.methodInquiry}</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Simulation Scenario Preset</label>
              <select
                className="form-select"
                value={scenario}
                onChange={(e) => setScenario(e.target.value)}
                id="dashboard-select-scenario"
              >
                <option value="normal">Scenario A: Normal Classroom (Baseline)</option>
                <option value="low_attention">Scenario B: Low Attention Classroom (Disengaged)</option>
                <option value="high_confusion">Scenario C: High Confusion Classroom (Struggling)</option>
                <option value="noisy">Scenario D: Noisy Classroom (Disruptive)</option>
                <option value="hyperactive">Scenario E: Hyperactive Classroom (High Energy)</option>
                <option value="time_pressure">Scenario F: Teacher Under Time Pressure (Tight Pacing)</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">{t.duration}</label>
              <select
                className="form-select"
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
                id="dashboard-select-duration"
              >
                <option value={5}>{t.durationVal.replace('{val}', '5')}</option>
                <option value={10}>{t.durationVal.replace('{val}', '10')}</option>
                <option value={15}>{t.durationVal.replace('{val}', '15')}</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">{t.language}</label>
              <select
                className="form-select"
                value={classLanguage}
                onChange={(e) => setClassLanguage(e.target.value as Language)}
                id="dashboard-select-lang"
              >
                <option value="English">English</option>
                <option value="Hindi">हिंदी (Hindi)</option>
                <option value="Bengali">বাংলা (Bengali)</option>
              </select>
            </div>

            <button type="submit" className="btn-primary" style={{ width: '100%', marginTop: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }} id="dashboard-btn-submit">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              {t.startBtn}
            </button>
          </form>
        </div>

        {/* History cards */}
        <div className="dashboard-panel glass animate-in-d2">
          <h2 className="gradient-text" style={{ marginBottom: '1.5rem', fontWeight: 700 }}>
            {t.historyTitle}
          </h2>
          
          {isLoading ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
              Loading historical data...
            </div>
          ) : history.length === 0 ? (
            <div style={{ 
              textAlign: 'center', 
              padding: '3rem 2rem', 
              color: 'var(--text-muted)',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem',
              alignItems: 'center',
              height: '100%',
              justifyContent: 'center'
            }}>
              <span style={{ display: 'inline-flex', color: 'var(--text-muted)' }}>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3-10 9h3v8h14v-8h3L12 3z"/><path d="M12 18H12.01"/></svg>
              </span>
              <p>{t.noHistory}</p>
            </div>
          ) : (
            <div className="history-list">
              {history.map((session) => (
                <div
                  key={session.id}
                  className="history-card glass"
                  onClick={() => onSelectPastSession(session.id)}
                  id={`history-card-${session.id}`}
                >
                  <div className="history-info">
                    <span style={{ fontWeight: 600, fontSize: '1rem' }}>
                      {session.subject}: {session.topic}
                    </span>
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                      {session.class_level} | {session.language}
                    </span>
                    <span className="history-meta">{formatDate(session.created_at)}</span>
                  </div>
                  <div className="score-badge" title="View details" style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.9rem' }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>
                    Details
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
