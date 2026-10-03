import React, { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import authService from '../services/authService';


const ROLE_BADGES = {
  STUDENT: {
    bg: 'bg-emerald-950/60',
    border: 'border-emerald-800',
    text: 'text-emerald-300',
    dot: 'bg-emerald-400',
    label: 'Student',
  },
  ISSUER: {
    bg: 'bg-indigo-950/60',
    border: 'border-indigo-800',
    text: 'text-indigo-300',
    dot: 'bg-indigo-400',
    label: 'Issuer / Institution',
  },
  RECRUITER: {
    bg: 'bg-amber-950/60',
    border: 'border-amber-800',
    text: 'text-amber-300',
    dot: 'bg-amber-400',
    label: 'Recruiter / Employer',
  },
  ADMIN: {
    bg: 'bg-purple-950/60',
    border: 'border-purple-800',
    text: 'text-purple-300',
    dot: 'bg-purple-400',
    label: 'Platform Admin',
  },
};

const Dashboard = () => {
  const { currentUser, role, logout } = useAuth();
  const [profileData, setProfileData] = useState(null);
  const [isLoadingProfile, setIsLoadingProfile] = useState(false);
  const [apiError, setApiError] = useState(null);

  const email = currentUser?.email || 'Unknown';
  const userRole = role || currentUser?.role || 'STUDENT';
  const roleConfig = ROLE_BADGES[userRole] || ROLE_BADGES.STUDENT;

  const handleTestApiCall = async () => {
    setIsLoadingProfile(true);
    setApiError(null);
    try {
      const data = await authService.getCurrentUser();
      setProfileData(data);
    } catch (err) {
      setApiError(
        err.response?.data?.detail || 'Failed to fetch current user profile from /users/me/'
      );
    } finally {
      setIsLoadingProfile(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Navigation */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="h-9 w-9 rounded-xl bg-indigo-600 flex items-center justify-center font-bold text-lg text-white shadow-lg shadow-indigo-500/30">
              E
            </div>
            <div>
              <span className="font-bold text-white text-base tracking-tight">Educhain</span>
              <span className="text-xs text-slate-400 block -mt-0.5">Credential Verification Platform</span>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            <div
              className={`hidden sm:flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border ${roleConfig.bg} ${roleConfig.border} ${roleConfig.text}`}
            >
              <span className={`w-2 h-2 rounded-full ${roleConfig.dot} animate-pulse`}></span>
              <span>{roleConfig.label}</span>
            </div>

            <button
              onClick={logout}
              className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 hover:text-white text-slate-300 text-xs font-semibold rounded-lg border border-slate-700 transition"
            >
              Sign Out
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-5xl w-full mx-auto p-6 md:p-8 space-y-6">
        {/* Banner with user info required by user prompt */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 shadow-xl">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <p className="text-xs uppercase font-bold tracking-wider text-indigo-400">Dashboard</p>
              <h1 className="text-2xl sm:text-3xl font-bold text-white mt-1">
                Logged in as <span className="text-indigo-300">{email}</span> ({userRole})
              </h1>
              <p className="text-sm text-slate-400 mt-2">
                Authentication session is active. Access token is securely stored in memory.
              </p>
            </div>
            <div>
              <span
                className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold border ${roleConfig.bg} ${roleConfig.border} ${roleConfig.text}`}
              >
                <span className={`w-2 h-2 rounded-full ${roleConfig.dot}`}></span>
                {userRole}
              </span>
            </div>
          </div>
        </div>

        {/* Auth Details & Diagnostic Card */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Session Overview */}
          <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 space-y-4">
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
              Session Overview
            </h2>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between py-2 border-b border-slate-800/80">
                <span className="text-slate-400">Email:</span>
                <span className="font-mono text-slate-200">{email}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-slate-800/80">
                <span className="text-slate-400">Assigned Role:</span>
                <span className="font-mono text-indigo-300 font-semibold">{userRole}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-slate-800/80">
                <span className="text-slate-400">User ID:</span>
                <span className="font-mono text-xs text-slate-400">{currentUser?.id || 'Active'}</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-slate-400">Token Storage:</span>
                <span className="text-emerald-400 text-xs font-medium bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800">
                  In-Memory (XSS Protected)
                </span>
              </div>
            </div>
          </div>

          {/* Test Live Backend Endpoint */}
          <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 space-y-4 flex flex-col justify-between">
            <div>
              <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
                API Auth Verification
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Test the Axios request interceptor and backend JWT validation by querying{' '}
                <code className="text-indigo-300 font-mono">GET /api/v1/users/me/</code>.
              </p>
            </div>

            {apiError && (
              <div className="p-3 rounded-lg bg-red-950/50 border border-red-800 text-red-300 text-xs">
                {apiError}
              </div>
            )}

            {profileData && (
              <pre className="p-3 bg-slate-950 rounded-lg text-xs font-mono text-slate-300 border border-slate-800 overflow-x-auto max-h-36">
                {JSON.stringify(profileData, null, 2)}
              </pre>
            )}

            <button
              onClick={handleTestApiCall}
              disabled={isLoadingProfile}
              className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-950 text-white text-xs font-semibold rounded-lg transition duration-150 flex items-center justify-center space-x-2"
            >
              {isLoadingProfile ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  <span>Calling /users/me/...</span>
                </>
              ) : (
                <span>Fetch Current User (/users/me/)</span>
              )}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Dashboard;
