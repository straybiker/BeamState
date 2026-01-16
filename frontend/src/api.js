import axios from 'axios';

// Environment variable or default to relative path /api (proxied by Nginx or Vite)
const API_URL = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
    baseURL: API_URL,
});

export default api;
