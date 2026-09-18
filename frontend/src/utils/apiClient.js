import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for attaching auth token (Phase 2)
apiClient.interceptors.request.use(
  (config) => {
    // Access token will be attached from memory in Phase 2
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for token refresh handling (Phase 2)
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    // Refresh token flow will be implemented in Phase 2
    return Promise.reject(error);
  }
);

export default apiClient;
