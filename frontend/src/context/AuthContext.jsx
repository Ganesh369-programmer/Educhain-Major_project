import React, { createContext, useState, useEffect, useCallback } from 'react';
import authService from '../services/authService';

import {
  setAuthTokens,
  clearAuthTokens,
  getRefreshToken,
  setOnAuthFailure,
  setOnTokenRefreshed,
} from '../utils/apiClient';

/**
 * =============================================================================
 * AuthContext — In-Memory Authentication State Management
 * =============================================================================
 *
 * WHY TOKENS ARE KEPT IN MEMORY (NOT localStorage):
 * Per docs/AUTHENTICATION.md and security best practices:
 * 1. XSS Vulnerability: Any JavaScript running on the page (including malicious
 *    scripts from compromised third-party npm packages or CDNs) can freely read
 *    window.localStorage. By keeping the JWT access token and refresh token strictly
 *    in JavaScript memory (React state and closure variables), scripts cannot
 *    directly steal credentials via `localStorage.getItem()`.
 * 2. Short-Lived Access: The access token has a short lifetime (15-30 mins).
 *    Even if captured during transmission, its window of validity is tiny.
 * 3. Trade-off: Refreshing or closing the browser tab clears in-memory state,
 *    requiring the user to log in again. This intentional security trade-off is
 *    documented in docs/AUTHENTICATION.md.
 * =============================================================================
 */

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  // Current authenticated user profile { id, email, role, ... }
  const [currentUser, setCurrentUser] = useState(null);

  // In-memory access token string (held in React state)
  const [accessToken, setAccessToken] = useState(null);

  // Authenticated user role: 'ADMIN' | 'STUDENT' | 'ISSUER' | 'RECRUITER'
  const [role, setRole] = useState(null);

  // Loading state (e.g. while authenticating or fetching current user)
  const [loading, setLoading] = useState(false);

  // True if user has an active, valid in-memory session
  const isAuthenticated = Boolean(accessToken && currentUser);

  /**
   * Complete logout:
   * 1. Informs backend to blacklist the refresh token on the server.
   * 2. Clears client-side in-memory tokens.
   * 3. Resets React state.
   */
  const logout = useCallback(async () => {
    try {
      const activeRefreshToken = getRefreshToken();
      if (activeRefreshToken) {
        // Best effort: blacklist the refresh token on the server
        await authService.logout(activeRefreshToken);
      }
    } catch {
      // Ignore network/blacklist errors during logout cleanup
    } finally {
      clearAuthTokens();
      setAccessToken(null);
      setCurrentUser(null);
      setRole(null);
    }
  }, []);

  /**
   * Set up interceptor listeners from apiClient on mount:
   * - On silent refresh failure: automatically log out the user.
   * - On silent token refresh success: update the in-memory accessToken state.
   */
  useEffect(() => {
    setOnAuthFailure(() => {
      clearAuthTokens();
      setAccessToken(null);
      setCurrentUser(null);
      setRole(null);
    });

    setOnTokenRefreshed((newToken) => {
      setAccessToken(newToken);
    });
  }, []);

  /**
   * Perform user login:
   * 1. Sends credentials to POST /api/v1/auth/login/.
   * 2. Receives { access, refresh, role }.
   * 3. Stores tokens in memory via apiClient.
   * 4. Fetches full profile via GET /api/v1/users/me/.
   */
  const login = async (email, password) => {
    setLoading(true);
    try {
      const data = await authService.login({ email, password });
      const { access, refresh, role: userRole } = data;

      // Update in-memory storage for apiClient Authorization headers
      setAuthTokens({ accessToken: access, refreshToken: refresh });
      setAccessToken(access);
      setRole(userRole);

      // Fetch user profile from /users/me/
      try {
        const userProfile = await authService.getCurrentUser();
        setCurrentUser(userProfile);
        return { success: true, user: userProfile };
      } catch {
        // Fallback user object if /users/me/ is temporarily slow/unavailable
        const basicUser = { email, role: userRole };
        setCurrentUser(basicUser);
        return { success: true, user: basicUser };
      }
    } finally {
      setLoading(false);
    }
  };

  const value = {
    currentUser,
    role,
    accessToken,
    isAuthenticated,
    loading,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export { AuthContext };
export default AuthContext;

