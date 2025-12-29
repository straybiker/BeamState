import axios from 'axios';

// Environment variable or default to localhost for dev
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
    baseURL: API_URL,
});

export default api;
