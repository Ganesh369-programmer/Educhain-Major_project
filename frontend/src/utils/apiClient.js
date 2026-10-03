import axios from 'axios';

// Base URL defaults to http://localhost:8000/api/v1 per API_SPECIFICATION.md
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

// Primary axios instance for all app requests
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * In-Memory Token Management
 * Per docs/AUTHENTICATION.md:
 * Tokens are kept in memory (module closure / React state), NEVER in localStorage.
 * This prevents Cross-Site Scripting (XSS) attacks from stealing tokens via script injection.
 */
let inMemoryAccessToken = null;
let inMemoryRefreshToken = null;
let onAuthFailureCallback = null;
let onTokenRefreshedCallback = null;

export const setAuthTokens = ({ accessToken, refreshToken }) => {
  inMemoryAccessToken = accessToken || null;
  if (refreshToken !== undefined) {
    inMemoryRefreshToken = refreshToken || null;
  }
};

export const clearAuthTokens = () => {
  inMemoryAccessToken = null;
  inMemoryRefreshToken = null;
};

export const getAccessToken = () => inMemoryAccessToken;
export const getRefreshToken = () => inMemoryRefreshToken;

export const setOnAuthFailure = (callback) => {
  onAuthFailureCallback = callback;
};

export const setOnTokenRefreshed = (callback) => {
  onTokenRefreshedCallback = callback;
};

// Request Interceptor: automatically attach Authorization header
apiClient.interceptors.request.use(
  (config) => {
    if (inMemoryAccessToken) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${inMemoryAccessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Concurrency control for silent token refresh
let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach((promise) => {
    if (error) {
      promise.reject(error);
    } else {
      promise.resolve(token);
    }
  });
  failedQueue = [];
};

// Response Interceptor: intercept 401 TOKEN_EXPIRED and silently refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Avoid infinite loops on auth endpoints (login, refresh, logout)
    const isAuthEndpoint =
      originalRequest?.url?.includes('/auth/refresh/') ||
      originalRequest?.url?.includes('/auth/login/');

    const status = error.response ? error.response.status : null;
    const errorCode = error.response?.data?.code;

    // Backend returns 401 with code 'TOKEN_EXPIRED' or 'UNAUTHENTICATED' when access token expires
    const isExpired = errorCode === 'TOKEN_EXPIRED' || (status === 401 && errorCode === 'UNAUTHENTICATED');

    if (status === 401 && isExpired && !originalRequest?._retry && !isAuthEndpoint && inMemoryRefreshToken) {
      if (isRefreshing) {
        // If a refresh is already in-flight, queue this request
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            return apiClient(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        // Use a clean axios instance to avoid triggering this interceptor again
        const refreshResponse = await axios.post(`${API_BASE_URL}/auth/refresh/`, {
          refresh: inMemoryRefreshToken,
        });

        const newAccessToken = refreshResponse.data.access;
        inMemoryAccessToken = newAccessToken;

        if (onTokenRefreshedCallback) {
          onTokenRefreshedCallback(newAccessToken);
        }

        processQueue(null, newAccessToken);

        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        // Refresh token is expired or invalid (REFRESH_INVALID)
        processQueue(refreshError, null);
        clearAuthTokens();

        if (onAuthFailureCallback) {
          onAuthFailureCallback(refreshError);
        }

        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default apiClient;
