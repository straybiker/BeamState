import axios from 'axios';

// Environment variable or default to current hostname on port 8000
const API_URL = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`;

const api = axios.create({
    baseURL: API_URL,
});

export default api;
