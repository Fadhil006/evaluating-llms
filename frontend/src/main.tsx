import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import { useEffect, useState } from 'react'
import Models from './Models'
import Datasets from './Datasets'
import Experiments from './Experiments'
import HumanReview from './HumanReview'
import './style.css'

type Health = { status: string; database: string }
type Settings = {
  execution_mode: 'live' | 'demo'
  free_only: boolean
  request_timeout_seconds: number
  providers_configured: Record<string, boolean>
}

const pages = ['Overview', 'Models', 'Datasets', 'Experiments', 'Human Review', 'Settings'] as const
const url = (name: string) => name === 'Overview' ? '/' : `/${name.toLowerCase().replaceAll(' ', '-')}`

function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    Promise.all([
      fetch('/api/health').then(response => { if (!response.ok) throw Error(); return response.json() as Promise<Health> }),
      fetch('/api/settings').then(response => { if (!response.ok) throw Error(); return response.json() as Promise<Settings> }),
    ]).then(([status, config]) => { setHealth(status); setSettings(config) }).catch(() => setError(true))
  }, [])

  return <div className="min-h-screen bg-slate-50 text-slate-900">
    <header className="border-b bg-white px-6 py-5">
      <h1 className="text-2xl font-semibold">LLM Comparison Lab</h1>
      <p className="text-sm text-slate-600">Local research workspace · single-user</p>
    </header>
    {settings?.execution_mode === 'demo' && <p role="status" className="bg-amber-100 px-6 py-3 font-bold text-amber-950">DEMONSTRATION MODE — synthetic fixture outputs only; no live provider calls or real model measurements</p>}
    <div className="mx-auto flex max-w-5xl flex-col gap-6 p-6 md:flex-row">
      <nav aria-label="Main navigation" className="flex shrink-0 flex-wrap gap-2 md:w-48 md:flex-col">
        {pages.map(name => <NavLink key={name} to={url(name)} end className={({ isActive }) => `rounded px-3 py-2 hover:bg-slate-200 focus-visible:outline-2 ${isActive ? 'bg-slate-900 text-white hover:bg-slate-800' : 'text-slate-800'}`}>{name}</NavLink>)}
      </nav>
      <main className="min-w-0 flex-1 rounded border border-slate-200 bg-white p-6">
        <Routes>
          <Route path="/" element={<section><h2 className="text-xl font-semibold">Overview</h2><p className="mt-3">Backend: {error ? 'Unavailable' : health ? health.status === 'ok' ? 'Connected' : 'Unavailable' : 'Checking…'}</p><p>Database: {health?.database ?? 'Unknown'}</p><p className="mt-4 text-slate-600">{settings?.execution_mode === 'demo' ? 'Demo mode runs synthetic fixtures through the local experiment queue. These outputs are not live model measurements.' : 'Discover currently verified-free routes, design and run comparisons, inspect task-specific scores, then review answers anonymously.'}</p></section>} />
          <Route path="/settings" element={<section><h2 className="text-xl font-semibold">Settings</h2>{settings ? <dl className="mt-3 space-y-2"><div><dt className="inline font-medium">Mode: </dt><dd className="inline">{settings.execution_mode}</dd></div><div><dt className="inline font-medium">Free-only: </dt><dd className="inline">{settings.free_only ? 'Required' : 'Unavailable'}</dd></div><div><dt className="inline font-medium">Request timeout: </dt><dd className="inline">{settings.request_timeout_seconds} seconds</dd></div>{Object.entries(settings.providers_configured).map(([name, configured]) => <div key={name}><dt className="inline font-medium">{name}: </dt><dd className="inline">{configured ? settings.execution_mode === 'demo' ? 'Key configured but ignored in demo mode' : 'Key configured (connection not checked)' : 'No key configured — unavailable'}</dd></div>)}</dl> : <p className="mt-3">{error ? 'Backend unavailable. Start the API to read settings.' : 'Checking…'}</p>}<p className="mt-4 text-slate-600">{settings?.execution_mode === 'demo' ? 'Live provider keys are never used in demonstration mode.' : 'Configuration is read-only in this phase.'}</p></section>} />
          <Route path="/models" element={<Models mode={settings?.execution_mode} />} />
          <Route path="/datasets" element={<Datasets />} />
          <Route path="/experiments" element={<Experiments mode={settings?.execution_mode} />} />
          <Route path="/human-review" element={<HumanReview />} />
          <Route path="*" element={<p>Page not found. Choose a section from the navigation.</p>} />
        </Routes>
      </main>
    </div>
  </div>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><BrowserRouter><App /></BrowserRouter></React.StrictMode>)
