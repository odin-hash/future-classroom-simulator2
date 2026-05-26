const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

export const API_BASE_URL =
  (import.meta.env.VITE_API_URL as string) ||
  (isLocal ? 'http://localhost:8000' : 'https://future-classroom-backend.onrender.com');

// Dynamically derive WebSocket URL from API_BASE_URL if not explicitly configured
export const WS_BASE_URL =
  (import.meta.env.VITE_WS_URL as string) ||
  API_BASE_URL.replace(/^http/, 'ws');

