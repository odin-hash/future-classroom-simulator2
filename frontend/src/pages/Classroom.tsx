import React, { useState, useEffect, useRef } from 'react';
import { TRANSLATIONS } from '../localization';
import type { Language } from '../localization';
import { StudentCard } from '../components/StudentCard';
import { VolumeControl } from '../components/VolumeControl';
import { EventPopup } from '../components/EventPopup';
import { Blackboard } from '../components/Blackboard';
import { API_BASE_URL } from '../config';
import { SYLLABUS } from '../syllabus';


interface ClassroomProps {
  sessionId: number;
  language: Language;
  onEndSession: (sessionId: number) => void;
  onExit: () => void;
}

interface Student {
  name: string;
  personality: string;
  avatar_style: string;
}

interface Message {
  id?: number;
  sender_type: 'teacher' | 'student' | 'system';
  sender_name: string;
  message_text: string;
  student_personality?: string;
}

interface EventDetail {
  id: string;
  title: string;
  description: string;
  severity: string;
  instructions: string;
  affected_students: string[];
}

export const Classroom: React.FC<ClassroomProps> = ({
  sessionId,
  language,
  onEndSession,
  onExit,
}) => {
  const t = TRANSLATIONS[language];
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Classroom States
  const [sessionDetails, setSessionDetails] = useState<any>(null);
  const [students, setStudents] = useState<Student[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  
  // Track emotional/focus state of each student by name
  const [studentEmotions, setStudentEmotions] = useState<Record<string, any>>({});
  const [activeSpeaker, setActiveSpeaker] = useState<string | null>(null);
  const [activeSpeakerText, setActiveSpeakerText] = useState<string | null>(null);
  const [activeEvent, setActiveEvent] = useState<EventDetail | null>(null);
  
  // Input and API status states
  const [teacherInput, setTeacherInput] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const [pendingStudent, setPendingStudent] = useState<string | null>(null);
  const [simulationError, setSimulationError] = useState<string | null>(null);
  const [lastMessageArgs, setLastMessageArgs] = useState<{ messageText: string, addressedStudent?: string, actionType?: string } | null>(null);
  const [isInputFocused, setIsInputFocused] = useState(false);
  const [viewMode, setViewMode] = useState<'gallery' | 'whiteboard'>('gallery');
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [showSyllabus, setShowSyllabus] = useState(false);
  const [showExitWarning, setShowExitWarning] = useState<false | 'exit' | 'end' | 'logo'>(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  // Timer states
  const [timeLeft, setTimeLeft] = useState(600); // 10 minutes default in seconds
  const [timerActive, setTimerActive] = useState(true);

  // STT configuration and Native SpeechRecognition Fallback
  const [hasSttKeys, setHasSttKeys] = useState<boolean>(true);
  const recognitionRef = useRef<any>(null);

  // Audio queue and volume states for premium neural voice playback
  const [isMuted, setIsMuted] = useState(false);
  const [volume, setVolume] = useState(0.85);
  const audioQueueRef = useRef<{ text: string; studentName: string; emotion: string }[]>([]);
  const isAudioPlayingRef = useRef(false);
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const originalEmotionsRef = useRef<Record<string, string>>({});
  const wasMicEnabledRef = useRef(false);
  const handleSendTurnRef = useRef<any>(null);
  const isTurnProcessingRef = useRef(false);
  const activeUtteranceRef = useRef<any>(null);

  // VAD and MediaRecorder state/refs
  const [isSpeaking, setIsSpeaking] = useState(false);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const vadIntervalRef = useRef<any>(null);
  const silenceStartRef = useRef<number | null>(null);
  const isRecordingRef = useRef(false);

  // 1. Fetch Session Info & Students list
  useEffect(() => {
    // Get students list
    fetch(`${API_BASE_URL}/api/students`)
      .then((res) => res.json())
      .then((data) => {
        setStudents(data);
        // Initialize all student emotions to normal
        const emotions: Record<string, string> = {};
        data.forEach((s: Student) => {
          emotions[s.name] = 'normal';
        });
        setStudentEmotions(emotions);
      });

    // Get specific session configuration
    fetch(`${API_BASE_URL}/api/sessions/${sessionId}`)
      .then((res) => res.json())
      .then((data) => {
        setSessionDetails(data);
        setMessages(data.messages || []);
        setTimeLeft(data.duration_minutes * 60);
      });

    // Fetch STT keys availability configuration
    fetch(`${API_BASE_URL}/api/config`)
      .then((res) => res.json())
      .then((data) => {
        setHasSttKeys(!!data.has_stt_keys);
      })
      .catch((err) => {
        console.warn("Failed to fetch API config, defaulting to server transcription:", err);
        setHasSttKeys(true);
      });
  }, [sessionId]);

  // 2. Ticking Countdown Timer
  useEffect(() => {
    if (!timerActive || timeLeft <= 0) return;
    const timer = setInterval(() => {
      setTimeLeft((prev) => prev - 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [timerActive, timeLeft]);

  // 3. Scroll to bottom of chat transcript
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isPending]);

  // 4. Cleanup VAD on unmount
  useEffect(() => {
    return () => {
      if (vadIntervalRef.current) {
        clearInterval(vadIntervalRef.current);
      }
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (audioContextRef.current) {
        if (audioContextRef.current.state !== 'closed') {
          audioContextRef.current.close();
        }
      }
    };
  }, []);

  // 4b. Initialize Native Speech Recognition Fallback (used when no server STT keys exist)
  useEffect(() => {
    if (hasSttKeys) {
      return;
    }

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRecognition) {
      const rec = new SpeechRecognition();
      rec.continuous = false;
      rec.interimResults = false;
      
      if (language === 'Hindi') {
        rec.lang = 'hi-IN';
      } else if (language === 'Bengali') {
        rec.lang = 'bn-IN';
      } else {
        rec.lang = 'en-US';
      }

      rec.onstart = () => {
        setIsListening(true);
      };

      rec.onresult = (event: any) => {
        const transcriptText = event.results[0][0].transcript;
        setTeacherInput(transcriptText);
        if (transcriptText.trim()) {
          console.info("[Native Mic Auto-Send] Speech recognized:", transcriptText);
          handleSendTurnRef.current?.(transcriptText);
        }
      };

      rec.onerror = (e: any) => {
        console.error('Native speech recognition error:', e);
        setIsListening(false);
      };

      rec.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current = rec;
    }

    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch (e) {}
      }
    };
  }, [language, hasSttKeys]);

  // iOS Safari touch audio context & SpeechSynthesis unlocker
  useEffect(() => {
    const unlockAudio = () => {
      // 1. Unlock web audio / new Audio()
      const contextClass = (window.AudioContext || (window as any).webkitAudioContext);
      if (contextClass) {
        try {
          const ctx = new contextClass();
          const buffer = ctx.createBuffer(1, 1, 22050);
          const source = ctx.createBufferSource();
          source.buffer = buffer;
          source.connect(ctx.destination);
          source.start(0);
          ctx.resume();
        } catch (e) {
          console.warn("[AudioContext Unlock] Failed:", e);
        }
      }
      
      // 2. Unlock SpeechSynthesis
      if ('speechSynthesis' in window) {
        try {
          const u = new SpeechSynthesisUtterance('');
          u.volume = 0;
          window.speechSynthesis.speak(u);
          console.info("[SpeechSynthesis Unlock] Executed silent utterance on user gesture.");
        } catch (e) {
          console.warn("[SpeechSynthesis Unlock] Failed:", e);
        }
      }
      
      // 3. Unlock HTML5 Audio() autoplay
      try {
        const silentMp3 = "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAAA";
        const unlockAudioObj = new Audio(silentMp3);
        unlockAudioObj.volume = 0;
        unlockAudioObj.play()
          .then(() => console.info("[HTML5 Audio Autoplay Unlock] HTML5 Audio successfully unlocked!"))
          .catch((err) => console.warn("[HTML5 Audio Autoplay Unlock] Play rejected:", err));
      } catch (err) {
        console.warn("[HTML5 Audio Autoplay Unlock] Failed:", err);
      }
      
      // Remove listeners after first run
      window.removeEventListener('click', unlockAudio);
      window.removeEventListener('touchstart', unlockAudio);
    };

    window.addEventListener('click', unlockAudio);
    window.addEventListener('touchstart', unlockAudio);

    return () => {
      window.removeEventListener('click', unlockAudio);
      window.removeEventListener('touchstart', unlockAudio);
    };
  }, []);

  // 5. Text-To-Speech (TTS) Voice Handler with Queuing & Piper Backend Support
  const speakStudentResponse = (text: string, studentName: string, emotion: string) => {
    // Queue the spoken item
    audioQueueRef.current.push({ text, studentName, emotion });
    
    // If not already playing, start the playback process immediately
    if (!isAudioPlayingRef.current) {
      processAudioQueue();
    }
  };

  // Core TTS queue play coordinator
  const processAudioQueue = async () => {
    if (audioQueueRef.current.length === 0) {
      isAudioPlayingRef.current = false;
      return;
    }

    // Ensure VAD recording is paused while speech is active to avoid self-feedback loops
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop();
      } catch (e) {}
    }
    isRecordingRef.current = false;
    silenceStartRef.current = null;

    // Ensure native speech recognition is aborted to avoid picking up student voice output
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch (e) {}
    }

    isAudioPlayingRef.current = true;
    const { text, studentName, emotion } = audioQueueRef.current[0];

    // 1. Temporarily save the student's emotion to restore later
    setStudentEmotions((prev) => {
      const restored = { ...prev };
      // Save the target emotion (the one they got from Gemini) so we can return to it later
      originalEmotionsRef.current[studentName] = emotion;
      // Do NOT set mouth talking animation - keep their original emotion
      restored[studentName] = emotion || 'normal';
      return restored;
    });
    
    // Trigger active speaker bubble in the UI
    setActiveSpeaker(studentName);
    setActiveSpeakerText(text);

    // Helper to cleanup and play next
    const handleSpeechEnded = () => {
      // Restore student's emotion back to their post-response baseline
      setStudentEmotions((prev) => {
        const restored = { ...prev };
        restored[studentName] = originalEmotionsRef.current[studentName] || 'normal';
        return restored;
      });
      
      // Clear active speaker bubble after a short delay
      setTimeout(() => {
        setActiveSpeakerText((prevText) => {
          if (prevText === text) {
            setActiveSpeaker(null);
            return null;
          }
          return prevText;
        });
      }, 1500);

      // De-queue the spoken item and recurse to play the next one
      audioQueueRef.current.shift();
      
      // Check if there are no more items left in the queue!
      if (audioQueueRef.current.length === 0) {
        isAudioPlayingRef.current = false;
        // Resume voice recognition if it was enabled
        if (wasMicEnabledRef.current) {
          if (hasSttKeys) {
            console.info("[Mic Auto-Resume] Audio queue empty. VAD listening automatically resumed.");
          } else if (recognitionRef.current) {
            try {
              recognitionRef.current.start();
              console.info("[Mic Auto-Resume] Audio queue empty. Native listening resumed.");
            } catch (e) {
              console.warn("[Mic Auto-Resume] Failed to resume native listening:", e);
            }
          }
        }
      } else {
        processAudioQueue();
      }
    };

    // If muted, just bypass audio playing instantly but keep the text/animation triggers flowing for realism
    if (isMuted) {
      // Simulate speaking time by calculating average reading speed (~180ms per word)
      const speakDelay = Math.max(1200, text.split(' ').length * 180);
      setTimeout(handleSpeechEnded, speakDelay);
      return;
    }

    // Try playing neural voice from Edge TTS backend
    let fallbackTriggered = false;
    let hasStartedPlaying = false;
    const triggerFallback = (reason: string) => {
      if (fallbackTriggered || hasStartedPlaying) return;
      fallbackTriggered = true;
      console.warn(`[TTS Fallback] Triggered fallback due to: ${reason}`);
      
      if (currentAudioRef.current) {
        try {
          currentAudioRef.current.pause();
          currentAudioRef.current.onended = null;
          currentAudioRef.current.onerror = null;
          currentAudioRef.current.onplay = null;
          currentAudioRef.current.onplaying = null;
        } catch (e) {}
        currentAudioRef.current = null;
      }
      
      playBrowserSpeechFallback(text, studentName, handleSpeechEnded);
    };

    try {
      const audioUrl = `${API_BASE_URL}/api/tts?text=${encodeURIComponent(text)}&student=${encodeURIComponent(studentName)}&language=${encodeURIComponent(language)}`;
      const audio = new Audio(audioUrl);
      audio.crossOrigin = "anonymous";
      currentAudioRef.current = audio;
      audio.volume = volume;

      audio.onplay = () => {
        hasStartedPlaying = true;
      };

      audio.onplaying = () => {
        hasStartedPlaying = true;
      };

      audio.onended = () => {
        handleSpeechEnded();
      };

      audio.onerror = () => {
        triggerFallback("audio.onerror");
      };

      await audio.play();
    } catch (err) {
      console.warn("[TTS Play Error] Play promise rejected:", err);
      triggerFallback("play promise catch");
    }
  };

  const playBrowserSpeechFallback = (text: string, studentName: string, onEnded: () => void) => {
    if (!('speechSynthesis' in window)) {
      onEnded();
      return;
    }

    // Cancel any previous speaking elements
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.volume = volume;

    // Set correct language property to ensure correct system voice matching
    if (language === 'Hindi') {
      utterance.lang = 'hi-IN';
    } else if (language === 'Bengali') {
      utterance.lang = 'bn-IN';
    } else {
      utterance.lang = 'en-US';
    }

    // Retain strong reference to prevent Safari garbage collection during playback
    activeUtteranceRef.current = utterance;

    // Resolve matched browser system voices
    const voices = window.speechSynthesis.getVoices();
    let matchingVoices = [];
    if (language === 'Hindi') {
      matchingVoices = voices.filter((v) => v.lang.startsWith('hi'));
    } else if (language === 'Bengali') {
      matchingVoices = voices.filter((v) => v.lang.startsWith('bn'));
    } else {
      matchingVoices = voices.filter((v) => v.lang.startsWith('en'));
    }

    // Prioritize neural voices
    matchingVoices.sort((a, b) => {
      const aGoogle = a.name.toLowerCase().includes('google');
      const bGoogle = b.name.toLowerCase().includes('google');
      const aNatural = a.name.toLowerCase().includes('natural');
      const bNatural = b.name.toLowerCase().includes('natural');
      if ((aGoogle || aNatural) && !(bGoogle || bNatural)) return -1;
      if (!(aGoogle || aNatural) && (bGoogle || bNatural)) return 1;
      return 0;
    });

    // Filter by gender if possible, otherwise distribute by index to ensure distinct student voices
    const isFemale = ['Ananya', 'Riya'].includes(studentName);
    let genderVoices = matchingVoices.filter((v) => {
      const nameLower = v.name.toLowerCase();
      if (isFemale) {
        return nameLower.includes('female') || 
               nameLower.includes('samantha') || 
               nameLower.includes('karen') || 
               nameLower.includes('moira') || 
               nameLower.includes('tessa') || 
               nameLower.includes('veena') || 
               nameLower.includes('siri') || 
               nameLower.includes('susan') || 
               nameLower.includes('hazel') || 
               nameLower.includes('zira') ||
               nameLower.includes('google हिन्दी') ||
               nameLower.includes('google বাংলা');
      } else {
        return nameLower.includes('male') || 
               nameLower.includes('daniel') || 
               nameLower.includes('brian') || 
               nameLower.includes('alex') || 
               nameLower.includes('fred') || 
               nameLower.includes('rishi') || 
               nameLower.includes('david') || 
               nameLower.includes('george') || 
               nameLower.includes('ravi');
      }
    });

    // Fallback to the entire voice list if no gender-specific voice is found
    if (genderVoices.length === 0) {
      genderVoices = matchingVoices;
    }

    // Map each student to a unique index offset to maximize vocal variance
    let voiceIndex = 0;
    switch (studentName) {
      case 'Aarav': voiceIndex = 0; break;
      case 'Ananya': voiceIndex = 1; break;
      case 'Vihaan': voiceIndex = 2; break;
      case 'Ishaan': voiceIndex = 3; break;
      case 'Riya': voiceIndex = 4; break;
      case 'Kabir': voiceIndex = 5; break;
      default: voiceIndex = 0;
    }

    const targetVoice = genderVoices[voiceIndex % genderVoices.length] || matchingVoices[0] || null;
    if (targetVoice) {
      utterance.voice = targetVoice;
    }

    // Apply specific pitch and rate multipliers matching character roles
    let pitch = 1.0;
    let rate = 1.0;
    switch (studentName) {
      case 'Aarav': // Curious (Arjun role: energetic, medium speed, enthusiastic)
        pitch = 0.95;
        rate = 1.0;
        break;
      case 'Ananya': // Shy (Priya role: soft, slower speaking, low confidence)
        pitch = 1.25;
        rate = 0.82;
        break;
      case 'Vihaan': // Distracted (Rahul role: casual, slightly lazy)
        pitch = 1.0;
        rate = 0.92;
        break;
      case 'Ishaan': // Hyperactive (Kabir role: fast speaking, excited)
        pitch = 1.15;
        rate = 1.08;
        break;
      case 'Riya': // Weak Learner (Neha role: slower, hesitant)
        pitch = 1.18;
        rate = 0.82;
        break;
      case 'Kabir': // Overconfident (Riya role: confident, quick speaking)
        pitch = 0.95;
        rate = 1.04;
        break;
      default:
        pitch = 1.0;
        rate = 1.0;
    }

    if (language === 'Hindi' || language === 'Bengali') {
      rate *= 0.9;
    }

    utterance.pitch = pitch;
    utterance.rate = rate;

    utterance.onend = () => {
      activeUtteranceRef.current = null;
      onEnded();
    };

    utterance.onerror = () => {
      activeUtteranceRef.current = null;
      onEnded();
    };

    window.speechSynthesis.speak(utterance);
  };

  // 6. Handle sending dialogue (turns) to backend
  const handleSendTurn = async (messageText: string, addressedStudent?: string, actionType?: string) => {
    if (isPending || isTurnProcessingRef.current) {
      console.warn("[handleSendTurn] Ignored duplicate turn submission: already processing.");
      return;
    }
    if (!messageText.trim() && !actionType) return;

    isTurnProcessingRef.current = true;
    setSimulationError(null);
    setLastMessageArgs({ messageText, addressedStudent, actionType });
    
    // Proactively trigger a silent speech utterance to unlock Safari SpeechSynthesis on user gesture
    if ('speechSynthesis' in window) {
      try {
        const u = new SpeechSynthesisUtterance(' ');
        u.volume = 0;
        window.speechSynthesis.speak(u);
      } catch (e) {
        console.warn("[SpeechSynthesis Proactive Unlock] Failed:", e);
      }
    }

    setIsPending(true);
    if (addressedStudent) {
      setPendingStudent(addressedStudent);
    } else {
      setPendingStudent(null);
    }
    setTeacherInput('');
    if (isListening) {
      if (hasSttKeys) {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
          try { mediaRecorderRef.current.stop(); } catch (e) {}
        }
        isRecordingRef.current = false;
        silenceStartRef.current = null;
      } else {
        if (recognitionRef.current) {
          try { recognitionRef.current.stop(); } catch (e) {}
        }
      }
    }

    // Add local optimistic teacher message to transcripts
    const tempTeacherMsg: Message = {
      sender_type: 'teacher',
      sender_name: 'Teacher',
      message_text: messageText || `[${actionType} student ${addressedStudent}]`,
    };
    setMessages((prev) => [...prev, tempTeacherMsg]);

    try {
      const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/turns`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: messageText || `Addressing ${addressedStudent}`,
          addressed_student: addressedStudent || null,
          action: actionType || null,
        }),
      });

      if (!response.ok) throw new Error('Turn processing failed');

      const data = await response.json();

      // If a system event was triggered, append to messages
      if (data.triggered_event) {
        setMessages((prev) => [
          ...prev,
          {
            sender_type: 'system',
            sender_name: `Event: ${data.triggered_event.title}`,
            message_text: data.triggered_event.description,
          },
        ]);
        setActiveEvent(data.triggered_event);

        // Update affected students emotions based on event
        setStudentEmotions((prev) => {
          const updated = { ...prev };
          data.triggered_event.affected_students.forEach((name: string) => {
            if (data.triggered_event.id === 'attention_drop') {
              updated[name] = 'sleeping';
            } else if (data.triggered_event.id === 'confusion') {
              updated[name] = 'confused';
            } else if (data.triggered_event.id === 'whispering') {
              updated[name] = 'distracted';
            } else if (data.triggered_event.id === 'interruption') {
              updated[name] = 'talking';
            } else {
              updated[name] = 'distracted';
            }
          });
          return updated;
        });
      }

      // If action resolved an event, clear event popup
      if (!data.active_event_id) {
        setActiveEvent(null);
      }

      // Handle student reply
      if (data.student_message) {
        const reply = data.student_message;
        
        // Append student reply to transcripts
        setMessages((prev) => [
          ...prev,
          {
            sender_type: 'student',
            sender_name: reply.sender_name,
            message_text: reply.message_text,
            student_personality: reply.student_personality,
          },
        ]);

        // Update speaker state & trigger bubble text above avatar
        setActiveSpeaker(reply.sender_name);
        setActiveSpeakerText(reply.message_text);

        // Update emotions
        setStudentEmotions((prev) => {
          const updated = { ...prev };
          // The active speaker gets the custom emotion from LLM
          updated[reply.sender_name] = reply.emotion;
          
          // If action was taken, return student to normal state
          if (addressedStudent && actionType) {
            updated[addressedStudent] = 'normal';
          }
          return updated;
        });

        // Trigger TTS to voice the student response
        speakStudentResponse(reply.message_text, reply.sender_name, reply.emotion);

        // Clear active speaker bubble text after 5 seconds
        setTimeout(() => {
          setActiveSpeakerText((prevText) => {
            if (prevText === reply.message_text) {
              setActiveSpeaker(null);
              return null;
            }
            return prevText;
          });
        }, 5000);
      }

    } catch (error) {
      console.error('Error submitting teacher input:', error);
      setSimulationError("The classroom intelligence failed to respond due to a temporary network timeout or API rate limit. Please try again.");
    } finally {
      isTurnProcessingRef.current = false;
      setIsPending(false);
      setPendingStudent(null);
    }
  };

  // Assign the ref so Speech Recognition can always invoke the latest handleSendTurn
  useEffect(() => {
    handleSendTurnRef.current = handleSendTurn;
  }, [handleSendTurn]);

  // 7. Micro-interactions: clicking button overlay on student card
  const handleStudentAction = (studentName: string, actionType: string) => {
    let actionLogText = '';
    if (actionType === 'focus') {
      actionLogText = t.refocusAction.replace('{name}', studentName);
    } else if (actionType === 're-engage') {
      actionLogText = t.wakeAction.replace('{name}', studentName);
    } else if (actionType === 'explain_basic') {
      actionLogText = t.explainAction.replace('{name}', studentName);
    } else {
      actionLogText = t.callingOn.replace('{name}', studentName);
    }

    // Trigger backend event processing
    handleSendTurn(actionLogText, studentName, actionType);
  };

  // Cleanup VAD and stop microphone
  const cleanupVAD = () => {
    if (vadIntervalRef.current) {
      clearInterval(vadIntervalRef.current);
      vadIntervalRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop();
      } catch (e) {
        console.error("[VAD cleanup] Stop recorder failed:", e);
      }
    }
    mediaRecorderRef.current = null;
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    if (audioContextRef.current) {
      if (audioContextRef.current.state !== 'closed') {
        audioContextRef.current.close();
      }
      audioContextRef.current = null;
    }
    analyserRef.current = null;
    audioChunksRef.current = [];
    silenceStartRef.current = null;
    isRecordingRef.current = false;
    setIsListening(false);
  };

  // Upload recorded speech blob to transcribe endpoint
  const uploadAndTranscribe = async (audioBlob: Blob, mimeType: string = 'audio/webm') => {
    try {
      setIsPending(true);
      const formData = new FormData();
      const fileExtension = mimeType.includes('mp4') ? 'mp4' : mimeType.includes('ogg') ? 'ogg' : 'webm';
      formData.append('file', audioBlob, `speech.${fileExtension}`);

      console.info(`[STT] Uploading recorded speech (${mimeType}) to /api/transcribe...`);
      const response = await fetch(`${API_BASE_URL}/api/transcribe`, {
        method: 'POST',
        headers: {
          'X-Audio-Mime-Type': mimeType
        },
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Failed to transcribe audio");
      }

      const data = await response.json();
      console.info("[STT] Transcribed successfully:", data.text);

      if (data.text && data.text.trim()) {
        await handleSendTurn(data.text);
      }
    } catch (e) {
      console.error("[STT] Upload/Transcription error:", e);
    } finally {
      setIsPending(false);
    }
  };

  // Start microphone VAD tracking
  const startVAD = async () => {
    try {
      // 1. Get User Media
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      // 2. Setup Web Audio
      const AudioContextClass = (window.AudioContext || (window as any).webkitAudioContext);
      const audioCtx = new AudioContextClass();
      audioContextRef.current = audioCtx;

      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      analyserRef.current = analyser;
      source.connect(analyser);

      setIsListening(true);

      // Start MediaRecorder IMMEDIATELY instead of waiting for a high silence threshold
      audioChunksRef.current = [];
      let options: MediaRecorderOptions = {};
      if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
        options = { mimeType: 'audio/webm;codecs=opus' };
      } else if (MediaRecorder.isTypeSupported('audio/webm')) {
        options = { mimeType: 'audio/webm' };
      } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
        options = { mimeType: 'audio/mp4' };
      } else if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) {
        options = { mimeType: 'audio/ogg;codecs=opus' };
      } else if (MediaRecorder.isTypeSupported('audio/ogg')) {
        options = { mimeType: 'audio/ogg' };
      }

      const mediaRecorder = new MediaRecorder(stream, options);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        console.log("[VAD] MediaRecorder stopped. Chunks:", audioChunksRef.current.length);
        if (audioChunksRef.current.length === 0) return;
        
        const recordedType = mediaRecorder.mimeType || 'audio/webm';
        const audioBlob = new Blob(audioChunksRef.current, { type: recordedType });
        audioChunksRef.current = [];
        
        await uploadAndTranscribe(audioBlob, recordedType);
      };

      try {
        mediaRecorder.start(100);
        isRecordingRef.current = true;
        console.log("[Mic] MediaRecorder started recording immediately.");
      } catch (err) {
        console.error("[Mic] Failed to start MediaRecorder:", err);
      }

      // 3. Set VAD checking loop (Only used to track speech presence and auto-submit after pause)
      const threshold = 0.005; // Lowered amplitude threshold (highly responsive)
      const bufferLength = analyser.fftSize;
      const dataArray = new Uint8Array(bufferLength);

      vadIntervalRef.current = setInterval(() => {
        if (!analyserRef.current || isAudioPlayingRef.current) return;
        analyserRef.current.getByteTimeDomainData(dataArray);

        // Calculate RMS amplitude
        let sumSquares = 0.0;
        for (let i = 0; i < bufferLength; i++) {
          const norm = (dataArray[i] - 128) / 128;
          sumSquares += norm * norm;
        }
        const rms = Math.sqrt(sumSquares / bufferLength);

        // Check if user is speaking
        const userIsSpeaking = rms > threshold;
        setIsSpeaking(userIsSpeaking);

        if (userIsSpeaking) {
          silenceStartRef.current = null;
        } else {
          // If silence is detected and we are currently recording
          if (isRecordingRef.current) {
            if (silenceStartRef.current === null) {
              silenceStartRef.current = Date.now();
            } else if (Date.now() - silenceStartRef.current > 2000) {
              console.log("[VAD] Silence detected for 2.0s. Stopping recording to transcribe.");
              if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
                try {
                  mediaRecorderRef.current.stop();
                } catch (e) {
                  console.error(e);
                }
              }
              isRecordingRef.current = false;
              silenceStartRef.current = null;
            }
          }
        }
      }, 50);

    } catch (err) {
      console.error("[VAD] Failed to initialize microphone VAD:", err);
      alert("Failed to access microphone. Please check permissions.");
      cleanupVAD();
    }
  };

  // Toggle voice recognition
  const toggleListening = () => {
    // Proactively trigger a silent speech utterance to unlock Safari SpeechSynthesis on user gesture
    if ('speechSynthesis' in window) {
      try {
        const u = new SpeechSynthesisUtterance(' ');
        u.volume = 0;
        window.speechSynthesis.speak(u);
      } catch (e) {
        console.warn("[SpeechSynthesis Proactive Unlock] Failed:", e);
      }
    }

    if (hasSttKeys) {
      if (isListening) {
        wasMicEnabledRef.current = false;
        cleanupVAD();
      } else {
        wasMicEnabledRef.current = true;
        startVAD();
      }
    } else {
      if (!recognitionRef.current) {
        alert('Speech Recognition is not supported by your browser. Please use Chrome, Edge, or Safari, or type in the input box.');
        return;
      }
      if (isListening) {
        wasMicEnabledRef.current = false;
        try { recognitionRef.current.stop(); } catch (e) {}
      } else {
        wasMicEnabledRef.current = true;
        try { recognitionRef.current.start(); } catch (e) {}
      }
    }
  };

  // Fetch active syllabus topics
  const getSyllabusTopics = (): string[] => {
    if (!sessionDetails) return [];
    const subj = sessionDetails.subject;
    const grade = sessionDetails.class_level;
    
    // Find matching subject key case-insensitively
    const syllabusSubjects = Object.keys(SYLLABUS);
    const matchedSubjectKey = syllabusSubjects.find(
      (s) => s.toLowerCase() === (subj || '').toLowerCase()
    );
    
    if (!matchedSubjectKey) return ["General Syllabus Guideline & Classroom Micro-Teaching Guidelines"];
    
    const gradesMap = SYLLABUS[matchedSubjectKey];
    const matchedGradeKey = Object.keys(gradesMap).find(
      (g) => g.toLowerCase() === (grade || '').toLowerCase()
    );
    
    return matchedGradeKey ? gradesMap[matchedGradeKey] : ["General course milestones for " + grade];
  };

  // Format timer text
  const formatTime = (secs: number) => {
    const minutes = Math.floor(secs / 60);
    const seconds = secs % 60;
    return `${minutes}${t.minutes} : ${seconds < 10 ? '0' : ''}${seconds}${t.seconds}`;
  };

  const hasActiveBubble = !!activeSpeaker || (isPending && !!pendingStudent);

  return (
    <div 
      className={`classroom-container ${isInputFocused ? 'classroom-dimmed' : ''} ${isChatOpen ? 'chat-open' : ''} ${isMobileMenuOpen ? 'mobile-menu-open' : ''} ${hasActiveBubble ? 'has-active-bubble' : ''}`}
      onClick={(e) => {
        // Automatically dismiss mobile rail menu if tapped outside
        if (isMobileMenuOpen && !(e.target as HTMLElement).closest('.left-nav-rail') && !(e.target as HTMLElement).closest('.mobile-hamburger-btn')) {
          setIsMobileMenuOpen(false);
        }
      }}
    >
      {/* Left Collapsing Navigation Rail */}
      <div className={`left-nav-rail ${isMobileMenuOpen ? 'open' : ''}`}>
        <div 
          className="nav-rail-logo" 
          onClick={() => { 
            setShowExitWarning('logo'); 
            setIsMobileMenuOpen(false); 
          }} 
          style={{ cursor: 'pointer' }}
        >
          <span style={{ display: 'inline-flex', color: 'var(--text-primary)' }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m12 3-10 9h3v8h14v-8h3L12 3z"/><path d="M12 18H12.01"/></svg>
          </span>
          <span className="nav-rail-label">Future Classroom</span>
        </div>
        
        <button 
          className="nav-rail-item active" 
          title={t.classroomStatus} 
          onClick={() => setIsMobileMenuOpen(false)}
          type="button"
        >
          <span style={{ display: 'inline-flex' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="20" height="14" x="2" y="3" rx="2"/><line x1="8" x2="16" y1="21" y2="21"/><line x1="12" x2="12" y1="17" y2="21"/></svg>
          </span>
          <span className="nav-rail-label">{t.classroomStatus}</span>
        </button>

        <button 
          className={`nav-rail-item ${showSyllabus ? 'active' : ''}`}
          title={`${t.topic}: ${sessionDetails?.topic || ''}`}
          onClick={() => {
            setShowSyllabus(true);
            setIsMobileMenuOpen(false);
          }}
          type="button"
        >
          <span style={{ display: 'inline-flex' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>
          </span>
          <span className="nav-rail-label">{sessionDetails?.subject || 'Subject'}</span>
        </button>

        <div style={{ flex: 1 }} />

        <button 
          className="nav-rail-item" 
          onClick={() => {
            setShowExitWarning('exit');
            setIsMobileMenuOpen(false);
          }}
          title={t.backBtn}
          id="classroom-btn-exit"
          type="button"
        >
          <span style={{ display: 'inline-flex' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/></svg>
          </span>
          <span className="nav-rail-label">{t.backBtn}</span>
        </button>

        <button 
          className="nav-rail-item" 
          style={{ color: 'var(--color-danger)' }}
          onClick={() => {
            setShowExitWarning('end');
            setIsMobileMenuOpen(false);
          }}
          title={t.endBtn}
          id="classroom-btn-end"
          type="button"
        >
          <span style={{ display: 'inline-flex' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><rect width="6" height="6" x="9" y="9"/></svg>
          </span>
          <span className="nav-rail-label">{t.endBtn}</span>
        </button>
      </div>

      {/* Top Header Navbar */}
      <div className="classroom-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1.5rem', boxSizing: 'border-box' }}>
        {/* Hamburger Menu Toggle Button for Mobile viewports */}
        <button
          className={`mobile-hamburger-btn ${isMobileMenuOpen ? 'active' : ''}`}
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          type="button"
          aria-label="Toggle Menu"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            {isMobileMenuOpen ? (
              <path d="M18 6L6 18M6 6l12 12" />
            ) : (
              <path d="M3 12h18M3 6h18M3 18h18" />
            )}
          </svg>
        </button>

        <div className="classroom-header-title" style={{ minWidth: 0, flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', margin: 0 }}>
            {sessionDetails?.subject}: <span className="gradient-text">{sessionDetails?.topic}</span>
          </h2>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', margin: 0 }}>
            {t.classLevel}: {sessionDetails?.class_level}
          </p>
        </div>

        {/* Segmented View Toggles */}
        <div className="view-toggle-bar">
          <button 
            className={`view-toggle-btn ${viewMode === 'gallery' ? 'active' : ''}`}
            onClick={() => setViewMode('gallery')}
            type="button"
          >
            <span style={{ display: 'inline-flex', alignItems: 'center' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: '6px' }}><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
              Gallery
            </span>
          </button>
          <button 
            className={`view-toggle-btn ${viewMode === 'whiteboard' ? 'active' : ''}`}
            onClick={() => setViewMode('whiteboard')}
            type="button"
          >
            <span style={{ display: 'inline-flex', alignItems: 'center' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: '6px' }}><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
              Whiteboard
            </span>
          </button>
        </div>
        
        <div className="classroom-header-right" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {/* Volume and Mute Control HUD */}
          <VolumeControl
            isMuted={isMuted}
            setIsMuted={setIsMuted}
            volume={volume}
            setVolume={setVolume}
          />

          {/* Countdown Clock */}
          <div 
            className="classroom-timer-wrapper"
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '0.5rem', 
              background: 'rgba(239, 68, 68, 0.08)', 
              padding: '0.4rem 0.8rem', 
              borderRadius: '8px',
              border: '1px solid rgba(239, 68, 68, 0.15)',
              fontWeight: 700,
              fontSize: '0.9rem',
              color: timeLeft < 60 ? 'var(--color-danger)' : 'var(--text-primary)'
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: '2px' }}><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            {formatTime(timeLeft)}
          </div>

          {/* Toggle Chat Drawer Button */}
          <button
            className={`transcript-toggle-btn btn-secondary ${isChatOpen ? 'active' : ''}`}
            style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem' }}
            onClick={() => setIsChatOpen(!isChatOpen)}
            type="button"
          >
            <span style={{ display: 'inline-flex', alignItems: 'center' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: '6px' }}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
              Transcript
            </span>
          </button>
        </div>
      </div>

      <div className="classroom-dimmed-layer">
        {/* Main Grid View */}
        <div className="classroom-grid-layout" style={{ gridTemplateColumns: '1fr' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', minHeight: 0 }}>
            {/* Active Event Banner */}
            <EventPopup event={activeEvent} />

            {viewMode === 'gallery' ? (
              /* Gallery View: Render student grid at full size */
              <div className="desks-grid" style={{ flex: 1, minHeight: 0 }}>
                {students.map((s) => (
                  <StudentCard
                    key={s.name}
                    student={s}
                    emotion={studentEmotions[s.name] || 'normal'}
                    isActiveSpeaker={activeSpeaker === s.name}
                    bubbleText={
                      activeSpeaker === s.name 
                        ? activeSpeakerText 
                        : (isPending && pendingStudent === s.name) 
                          ? '...' 
                          : null
                    }
                    onAction={handleStudentAction}
                  />
                ))}
              </div>
            ) : (
              /* Whiteboard View: Render Blackboard canvas and scaled student filmstrip */
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', flex: 1, minHeight: 0 }}>
                <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
                  <Blackboard 
                    onShare={(desc) => handleSendTurn(`[Illustrated ${desc} on Blackboard]`, undefined, 'blackboard_share')}
                    subject={sessionDetails?.subject || ''}
                    topic={sessionDetails?.topic || ''}
                  />
                </div>
                
                {/* Horizontal Filmstrip of Student Desks */}
                <div className="student-filmstrip">
                  {students.map((s) => (
                    <StudentCard
                      key={s.name}
                      student={s}
                      emotion={studentEmotions[s.name] || 'normal'}
                      isActiveSpeaker={activeSpeaker === s.name}
                      bubbleText={
                        activeSpeaker === s.name 
                          ? activeSpeakerText 
                          : (isPending && pendingStudent === s.name) 
                            ? '...' 
                            : null
                      }
                      onAction={handleStudentAction}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Right Side Sliding Chat Drawer */}
      <div className={`chat-drawer ${isChatOpen ? 'open' : ''}`}>
        <div className="transcript-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem', borderBottom: '1px solid var(--border-card)' }}>
          <span style={{ fontWeight: 700, display: 'flex', alignItems: 'center' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: '6px' }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" x2="8" y1="13" y2="13"/><line x1="16" x2="8" y1="17" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            {t.recentTranscript}
          </span>
          <button 
            className="btn-icon" 
            onClick={() => setIsChatOpen(false)}
            style={{ width: '30px', height: '30px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            type="button"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" x2="6" y1="6" y2="18"/><line x1="6" x2="18" y1="6" y2="18"/></svg>
          </button>
        </div>
        
        <div className="transcript-body">
          {messages.map((m, idx) => {
            const isAction = m.message_text.startsWith('[') && m.message_text.endsWith(']');
            return (
              <div 
                key={idx} 
                className={`chat-bubble ${m.sender_type} ${isAction ? 'action' : ''}`}
                id={`chat-bubble-${idx}`}
              >
                {m.sender_type !== 'system' && !isAction && (
                  <div className="chat-name">
                    {m.sender_name} {m.student_personality ? `(${m.student_personality})` : ''}
                  </div>
                )}
                <div className="chat-text">{m.message_text}</div>
              </div>
            );
          })}
          
          {isPending && (
            <div className="chat-bubble student" style={{ fontStyle: 'italic', opacity: 0.6, fontSize: '0.85rem' }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
                Student responding...
              </span>
            </div>
          )}

          {simulationError && (
            <div className="chat-bubble system error" style={{ 
              background: 'rgba(239, 68, 68, 0.15)', 
              borderLeft: '4px solid #ef4444', 
              borderRadius: '8px',
              padding: '0.85rem 1rem', 
              fontSize: '0.88rem', 
              color: 'var(--text-primary)',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.6rem',
              margin: '0.5rem 0'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, color: '#ef4444' }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/></svg>
                Classroom intelligence connection error
              </div>
              <div>{simulationError}</div>
              <button
                type="button"
                onClick={() => {
                  if (lastMessageArgs) {
                    handleSendTurn(lastMessageArgs.messageText, lastMessageArgs.addressedStudent, lastMessageArgs.actionType);
                  }
                }}
                style={{
                  alignSelf: 'flex-start',
                  background: '#ef4444',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '4px',
                  padding: '0.35rem 0.75rem',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.3rem',
                  transition: 'opacity 0.2s'
                }}
                onMouseOver={(e) => (e.currentTarget.style.opacity = '0.85')}
                onMouseOut={(e) => (e.currentTarget.style.opacity = '1')}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                Retry Turn
              </button>
            </div>
          )}
          
          <div ref={chatEndRef} />
        </div>
      </div>

      {/* Floating Action Dock centered at bottom center */}
      <div className="floating-action-dock">
        {/* Input form */}
        <form 
          onSubmit={(e) => {
            e.preventDefault();
            handleSendTurn(teacherInput);
          }}
          className="text-input-container"
          style={{ flex: 1, display: 'flex', alignItems: 'center', position: 'relative' }}
        >
          <input
            type="text"
            className="dock-input"
            value={teacherInput}
            onChange={(e) => setTeacherInput(e.target.value)}
            onFocus={() => setIsInputFocused(true)}
            onBlur={() => setIsInputFocused(false)}
            placeholder={isListening ? t.micListening : t.typePlaceholder}
            disabled={isPending}
            id="classroom-input-text"
            style={{ 
              flex: 1, 
              border: 'none', 
              background: 'transparent', 
              outline: 'none', 
              padding: '0.6rem 0',
              fontSize: '0.95rem',
              color: 'var(--text-primary)'
            }}
          />
          
          <div className="dock-action-buttons">
            {/* STT Mic trigger */}
             <button 
              className={`dock-mic-button ${isListening ? 'listening' : ''} ${isSpeaking ? 'speaking' : ''}`}
              onClick={toggleListening}
              title={isListening ? t.micListening : t.micIdle}
              id="classroom-btn-mic"
              type="button"
              style={{ 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                position: 'relative',
                zIndex: 10,
                flexShrink: 0,
                transform: isSpeaking ? 'scale(1.15)' : 'scale(1)',
                transition: 'all 0.15s ease-in-out',
                boxShadow: isSpeaking ? '0 0 20px #ef4444' : 'none'
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>
            </button>

            {/* Send button */}
            <button 
              type="submit" 
              className="dock-send-button"
              disabled={isPending || !teacherInput.trim()}
              id="classroom-btn-send"
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="22" x2="11" y1="2" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            </button>
          </div>
        </form>
      </div>

      {showSyllabus && (
        <div 
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            width: '100vw',
            height: '100vh',
            background: 'rgba(15, 23, 42, 0.4)',
            backdropFilter: 'blur(4px)',
            zIndex: 1200,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
          onClick={() => setShowSyllabus(false)}
        >
          <div 
            className="saas-card"
            style={{
              width: '90%',
              maxWidth: '480px',
              padding: '2rem',
              position: 'relative',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.15)',
              display: 'flex',
              flexDirection: 'column',
              gap: '1.25rem',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--primary)', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', textAlign: 'left' }}>
                  Syllabus Guideline
                </span>
                <h3 style={{ fontSize: '1.35rem', fontWeight: 800, color: 'var(--text-primary)', marginTop: '0.25rem', textAlign: 'left' }}>
                  {sessionDetails?.subject}
                </h3>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.15rem', textAlign: 'left' }}>
                  Grade Level: {sessionDetails?.class_level}
                </p>
              </div>
              <button 
                className="btn-icon"
                onClick={() => setShowSyllabus(false)}
                style={{ width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                type="button"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" x2="6" y1="6" y2="18"/><line x1="6" x2="18" y1="6" y2="18"/></svg>
              </button>
            </div>

            <div style={{ borderBottom: '1px solid var(--border-card)' }} />

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <h4 style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)', textAlign: 'left' }}>
                Required Course Modules:
              </h4>
              <ul style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', paddingLeft: '1.25rem', margin: 0 }}>
                {getSyllabusTopics().map((topicItem, index) => (
                  <li 
                    key={index} 
                    style={{ 
                      fontSize: '0.85rem', 
                      color: 'var(--text-secondary)',
                      lineHeight: 1.4,
                      textAlign: 'left'
                    }}
                  >
                    {topicItem}
                  </li>
                ))}
              </ul>
            </div>

            <div style={{ background: 'rgba(37, 99, 235, 0.04)', border: '1px solid rgba(37, 99, 235, 0.1)', padding: '1rem', borderRadius: '12px', marginTop: '0.5rem' }}>
              <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--primary)', display: 'block', marginBottom: '0.25rem', textAlign: 'left' }}>
                Trainee Guideline:
              </span>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.4, margin: 0, textAlign: 'left' }}>
                Design your lessons, blackboard illustrations, and student questions around these core curricular milestones to maximize your Pedagogical Assessment score.
              </p>
            </div>
          </div>
        </div>
      )}

      {showExitWarning && (
        <div 
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            width: '100vw',
            height: '100vh',
            background: 'rgba(15, 23, 42, 0.4)',
            backdropFilter: 'blur(4px)',
            zIndex: 1200,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
          onClick={() => setShowExitWarning(false)}
        >
          <div 
            className="saas-card"
            style={{
              width: '90%',
              maxWidth: '480px',
              padding: '2rem',
              position: 'relative',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.15)',
              display: 'flex',
              flexDirection: 'column',
              gap: '1.25rem',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--primary)', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', textAlign: 'left' }}>
                  {showExitWarning === 'logo' ? 'Platform Overview' : showExitWarning === 'exit' ? 'Exit to Dashboard' : 'End Class Session'}
                </span>
                <h3 style={{ fontSize: '1.35rem', fontWeight: 800, color: 'var(--text-primary)', marginTop: '0.25rem', textAlign: 'left' }}>
                  {showExitWarning === 'logo' ? 'Future Classroom Simulator' : 'Conclude active training?'}
                </h3>
              </div>
              <button 
                className="btn-icon"
                onClick={() => setShowExitWarning(false)}
                style={{ width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                type="button"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" x2="6" y1="6" y2="18"/><line x1="6" x2="18" y1="6" y2="18"/></svg>
              </button>
            </div>

            <div style={{ borderBottom: '1px solid var(--border-card)' }} />

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {showExitWarning === 'logo' ? (
                <>
                  <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', lineHeight: 1.5, textAlign: 'left', margin: 0 }}>
                    This high-fidelity interactive training environment allows teacher trainees to practice real-time classroom orchestration, lesson execution, and proactive student behavior management.
                  </p>
                  <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', lineHeight: 1.5, textAlign: 'left', margin: 0 }}>
                    Utilize the interactive whiteboard, observe active emotional responses from your 6 AI student personas, and use speech or text controls to lead your lesson plan.
                  </p>
                </>
              ) : showExitWarning === 'exit' ? (
                <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', lineHeight: 1.5, textAlign: 'left', margin: 0 }}>
                  Are you sure you want to exit the active classroom session and return to the dashboard? Your current session progress will be preserved.
                </p>
              ) : (
                <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', lineHeight: 1.5, textAlign: 'left', margin: 0 }}>
                  Are you sure you want to end this class? This will immediately conclude the teaching session, stop the timer, and generate your micro-teaching evaluation report.
                </p>
              )}
            </div>

            <div style={{ background: 'rgba(37, 99, 235, 0.04)', border: '1px solid rgba(37, 99, 235, 0.1)', padding: '1rem', borderRadius: '12px', marginTop: '0.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem', textAlign: 'left' }}>
                <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--primary)' }}>
                  Time Remaining:
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  {formatTime(timeLeft)}
                </span>
              </div>
              <div style={{ background: 'rgba(37, 99, 235, 0.1)', color: '#2563eb', padding: '0.4rem 0.8rem', borderRadius: '20px', fontSize: '0.75rem', fontWeight: 700 }}>
                Session In Progress
              </div>
            </div>

            <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem' }}>
              <button 
                className="btn-secondary" 
                style={{ flex: 1, padding: '0.65rem', fontSize: '0.85rem' }}
                onClick={() => setShowExitWarning(false)}
                type="button"
              >
                Keep Teaching
              </button>
              {showExitWarning === 'exit' ? (
                <button 
                  className="btn-primary" 
                  style={{ flex: 1, padding: '0.65rem', fontSize: '0.85rem', background: 'var(--color-danger)', border: 'none' }}
                  onClick={() => {
                    setShowExitWarning(false);
                    setTimerActive(false);
                    onExit();
                  }}
                  type="button"
                >
                  Exit Session
                </button>
              ) : (
                <button 
                  className="btn-primary" 
                  style={{ flex: 1, padding: '0.65rem', fontSize: '0.85rem', background: 'var(--color-danger)', border: 'none' }}
                  onClick={() => {
                    setShowExitWarning(false);
                    setTimerActive(false);
                    onEndSession(sessionId);
                  }}
                  type="button"
                >
                  End Class
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
