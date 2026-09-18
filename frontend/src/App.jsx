import React from 'react';

function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6">
      <div className="max-w-2xl w-full bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl space-y-6">
        <div className="flex items-center space-x-3">
          <div className="h-10 w-10 rounded-xl bg-indigo-600 flex items-center justify-center text-xl font-bold shadow-lg shadow-indigo-500/30">
            E
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">Educhain Platform</h1>
            <p className="text-sm text-slate-400">Blockchain-Based Academic Credential Verification</p>
          </div>
        </div>

        <div className="p-4 rounded-xl bg-slate-800/60 border border-slate-700/50">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-emerald-400 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              Phase 1 — Project Setup Active
            </span>
            <span className="text-xs bg-slate-700 text-slate-300 px-2 py-1 rounded">React + Vite + Tailwind</span>
          </div>
          <p className="text-xs text-slate-400 mt-2">
            Layer scaffolding complete: Backend (Django REST Framework), Frontend (React Vite + Tailwind), and Blockchain (Hardhat Ganache).
          </p>
        </div>

        <div className="grid grid-cols-3 gap-3 text-center text-xs">
          <div className="p-3 bg-slate-800/40 rounded-lg border border-slate-800">
            <span className="text-slate-400 block mb-1">Backend</span>
            <span className="text-slate-200 font-semibold">Django + DRF</span>
          </div>
          <div className="p-3 bg-slate-800/40 rounded-lg border border-slate-800">
            <span className="text-slate-400 block mb-1">Client</span>
            <span className="text-slate-200 font-semibold">React + Tailwind</span>
          </div>
          <div className="p-3 bg-slate-800/40 rounded-lg border border-slate-800">
            <span className="text-slate-400 block mb-1">Blockchain</span>
            <span className="text-slate-200 font-semibold">Hardhat / Ganache</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
