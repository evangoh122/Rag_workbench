import axios from 'axios';

export const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

const apiKey = import.meta.env.VITE_API_KEY as string | undefined;

const client = axios.create({
  baseURL: API_BASE,
  headers: apiKey ? { 'X-API-Key': apiKey } : {},
});

export default client;
