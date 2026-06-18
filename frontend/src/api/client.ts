import axios from 'axios';

export const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

const client = axios.create({
  baseURL: API_BASE,
});

// Check query param for api_key to save to localStorage
try {
  const urlParams = new URLSearchParams(window.location.search);
  const queryKey = urlParams.get('api_key');
  if (queryKey) {
    localStorage.setItem('api_key', queryKey);
    // Clean up the URL query param so it doesn't stay visible
    const cleanUrl = window.location.origin + window.location.pathname;
    window.history.replaceState({ path: cleanUrl }, '', cleanUrl);
  }
} catch (e) {
  console.warn('Failed to parse URL query params or update localStorage:', e);
}

client.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('api_key') || (import.meta.env.VITE_API_KEY as string | undefined);
  if (apiKey) {
    config.headers['X-API-Key'] = apiKey;
  }
  return config;
});

export default client;
