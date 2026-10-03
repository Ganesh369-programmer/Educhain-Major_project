import apiClient from '../utils/apiClient';

/**
 * Authentication Service
 * Mirrors endpoints defined in docs/API_SPECIFICATION.md:
 * - POST /auth/register/
 * - POST /auth/login/
 * - POST /auth/refresh/
 * - POST /auth/logout/
 * - GET  /users/me/
 */
export const authService = {
  /**
   * Register a new user with role STUDENT, ISSUER, or RECRUITER.
   * ADMIN cannot be self-registered.
   */
  async register({ email, password, role, phoneNumber }) {
    const payload = {
      email,
      password,
      role,
      ...(phoneNumber ? { phone_number: phoneNumber } : {}),
    };
    const response = await apiClient.post('/auth/register/', payload);
    return response.data; // { id, email, role }
  },

  /**
   * Log in with email and password.
   * Returns JWT tokens and user role.
   */
  async login({ email, password }) {
    const response = await apiClient.post('/auth/login/', { email, password });
    return response.data; // { access, refresh, role }
  },

  /**
   * Exchange a valid refresh token for a fresh access token.
   */
  async refresh(refreshToken) {
    const response = await apiClient.post('/auth/refresh/', { refresh: refreshToken });
    return response.data; // { access }
  },

  /**
   * Blacklist the refresh token on the server and terminate the session.
   */
  async logout(refreshToken) {
    const response = await apiClient.post('/auth/logout/', { refresh: refreshToken });
    return response.data;
  },

  /**
   * Retrieve the profile of the currently authenticated user.
   */
  async getCurrentUser() {
    const response = await apiClient.get('/users/me/');
    return response.data; // { id, email, role, profile, ... }
  },
};

export default authService;
