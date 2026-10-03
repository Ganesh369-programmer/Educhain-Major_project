import React from 'react';
import { Navigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';


/**
 * ProtectedRoute Component
 * Guards routes by checking authentication status and verifying required roles.
 *
 * Props:
 * - children: the protected component tree to render
 * - allowedRoles: string or array of permitted roles (e.g. ['ADMIN', 'ISSUER'])
 */
const ProtectedRoute = ({ children, allowedRoles }) => {
  const { isAuthenticated, currentUser, role, loading, logout } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="w-10 h-10 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
          <p className="text-slate-400 text-sm">Verifying session...</p>
        </div>
      </div>
    );
  }

  // 1. If not authenticated, redirect to /login and preserve destination
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // 2. If role restriction exists, verify user's role
  if (allowedRoles) {
    const rolesArray = Array.isArray(allowedRoles) ? allowedRoles : [allowedRoles];
    const userRole = role || currentUser?.role;

    if (!rolesArray.includes(userRole)) {
      return (
        <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-6">
          <div className="max-w-md w-full bg-slate-900 border border-red-900/50 rounded-2xl p-8 shadow-2xl text-center space-y-6">
            <div className="w-16 h-16 bg-red-950/60 border border-red-700/60 rounded-2xl flex items-center justify-center mx-auto text-red-400 text-3xl">
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
            </div>

            <div>
              <h1 className="text-2xl font-bold text-white">403 — Not Permitted</h1>
              <p className="text-sm text-slate-400 mt-2">
                Your account role <span className="font-semibold text-amber-400 font-mono">[{userRole || 'UNKNOWN'}]</span> does not have permission to view this section.
              </p>
              <p className="text-xs text-slate-500 mt-1">
                Required role: {rolesArray.join(' or ')}
              </p>
            </div>

            <div className="flex flex-col sm:flex-row gap-3 pt-2">
              <Link
                to="/dashboard"
                className="flex-1 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
              >
                Go to Dashboard
              </Link>
              <button
                onClick={logout}
                className="flex-1 px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium rounded-lg transition-colors border border-slate-700"
              >
                Log Out
              </button>
            </div>
          </div>
        </div>
      );
    }
  }

  // 3. Authenticated and role permitted
  return children;
};

export default ProtectedRoute;
