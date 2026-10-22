import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, type Dataset } from './Datasets'
import Datasets from './Datasets'
import ResultsPanel, { type DashboardReport } from './ResultsPanel'

type Model = { id: number; provider: string; model_id: string; name: string; endpoint: string; availability: string; credential_configured: boolean; pricing_source: string | null; supported_parameters: string[]; eligibility: { allowed: boolean; reason: string; checked_at: string | null; model_id: string } }
type Version = { dataset_id: number; version: string; content_sha256: string; category_inventory: Record<string, number>; manifest: Record<string, unknown>; items: { id: string; task_type: string; prompt: string; context: string | null; choices: string[] | null; reference_answers: unknown[]; scoring_config: Record<string, unknown>; tags: string[]; split: string; family_id: string | null; variant_id: string | null; source: string; license: string; review_status: string; provenance: Record<string, unknown> }[] }
type Provider = { slug: string; credential_configured: boolean; connection_status: string; checked_at: string | null }
type Budget = { initial_candidate_requests: number; maximum_candidate_retries: number; unconstrained_maximum_attempts: number; maximum_attempts: number; metadata_startup: number; metadata_refresh: number }
type Estimate = { estimate: Budget; item_ids: string[]; category_counts: Record<string, number>; ready: boolean; policy_decisions_advisory: { provider: string; model_id: string; allowed: boolean; reason: string }[] }
type Draft = { id: number; name: string; status: string; pause_reason?: string | null; provenance_mode: string; dataset_version_id: number; estimate: Budget; ready: boolean; config: { item_ids: string[]; attempt_cap: number; models: { provider: string; model_id: string }[] } }
type Progress = { status: string; pause_reason: string | null; completed: number; failed: number; pending: number; in_flight: number; cancelled: number; attempts_consumed: number; attempts_remaining: number; questions_completed?: number; questions_total?: number }
type Results = DashboardReport

function eligible(model: Model, mode?: 'live' | 'demo') {
  return mode === 'demo' ? model.provider === 'fixture' : model.eligibility?.allowed === true && model.credential_configured && !!model.eligibility.checked_at && model.eligibility.model_id === model.model_id && !!model.pricing_source && model.availability === 'available'
}

const policyHelp: Record<string, string> = {
  stale_pricing: 'Pricing evidence expired. Refresh the catalog; Zen may need a reviewed pricing update.',
  unknown_pricing: 'Pricing is unknown. Refresh the catalog or choose another verified-free route.',
  nonzero_or_invalid_pricing: 'This route has nonzero or invalid pricing. Choose a verified-free route.',
  official_price_evidence_required: 'No current official free-price evidence is available. Choose another route.',
  conditional_pricing: 'The price depends on conditions this app cannot verify. Choose another route.',
  unsupported_endpoint: 'This route requires an endpoint the app does not support. Choose another model.',
  unsupported_parameter: 'This route cannot accept a required request setting. Choose another model.',
  unavailable: 'The model is temporarily unavailable. Refresh later or explicitly choose another route.',
}

export default function Experiments({ mode }: { mode?: 'live' | 'demo' }) {
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [models, setModels] = useState<Model[]>([])
  const [providers, setProviders] = useState<Provider[]>([])
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [expandedDraftId, setExpandedDraftId] = useState<number | null>(null)
  const [progress, setProgress] = useState<Record<number, Progress>>({})
  const [results, setResults] = useState<Record<number, Results>>({})
  const [runErrors, setRunErrors] = useState<Record<number, string>>({})
  const [runBusy, setRunBusy] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [step, setStep] = useState(1)
  const [datasetId, setDatasetId] = useState('')
  const [version, setVersion] = useState('')
  const [versionId, setVersionId] = useState('')
  const [detail, setDetail] = useState<Version | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [modelA, setModelA] = useState('')
  const [modelB, setModelB] = useState('')
  const [providerFilter, setProviderFilter] = useState('all')
  const [modelSearch, setModelSearch] = useState('')
  const [showUnavailable, setShowUnavailable] = useState(false)
  const [name, setName] = useState('Beginner comparison')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [maxTokens, setMaxTokens] = useState(512)
  const [temperature, setTemperature] = useState('')
  const [repetitions, setRepetitions] = useState(1)
  const [seed, setSeed] = useState(42)
  const [timeout, setTimeout] = useState(60)
  const [retries, setRetries] = useState(0)
  const [attemptCap, setAttemptCap] = useState(40)
  const [estimate, setEstimate] = useState<Estimate | null>(null)
  const [estimateKey, setEstimateKey] = useState('')
  const [estimateBusy, setEstimateBusy] = useState(false)
  const [estimateError, setEstimateError] = useState('')
  const [questionChoice, setQuestionChoice] = useState<'sample' | 'own'>('sample')
  const [staleRouteIds, setStaleRouteIds] = useState<string[]>([])
  const [pendingDraftId, setPendingDraftId] = useState<number | null>(null)
  const [startedDraftId, setStartedDraftId] = useState<number | null>(null)
  const startLock = useRef(false)
  const stepHeading = useRef<HTMLHeadingElement>(null)

  async function reloadCatalog() {
    setBusy(true); setError(''); setNotice('Refreshing provider catalogs…')
    try {
      const refreshed = await api<Record<string, { status: string; reason?: string; models?: number }>>('/api/models/refresh', { method: 'POST' })
      const [catalog, connections] = await Promise.all([api<Model[]>('/api/models'), api<Provider[]>('/api/providers')])
      const retained = selectedModels.filter(model => !catalog.some(row => row.id === model.id))
      setStaleRouteIds(retained.map(model => String(model.id)))
      setModels([...catalog, ...retained]); setProviders(connections)
      setNotice(`Catalog refresh complete: ${Object.entries(refreshed).map(([provider, result]) => `${provider}: ${result.status}${result.reason ? ` (${result.reason})` : ''}`).join(' · ') || 'no providers reported'}`)
    } catch (cause) { setError((cause as Error).message); setNotice('') }
    finally { setBusy(false) }
  }

  useEffect(() => {
    let active = true
    Promise.all([api<Dataset[]>('/api/datasets'), api<Model[]>('/api/models'), api<Provider[]>('/api/providers'), api<Draft[]>('/api/experiments')])
      .then(async ([data, catalog, connectionRows, saved]) => {
        if (!active) return
        if (catalog.length === 0 || (connectionRows.some(provider => provider.credential_configured) && !catalog.some(model => eligible(model, mode)))) {
          setNotice('Loading provider catalogs. This checks model availability and pricing; it does not generate answers.')
          await api('/api/models/refresh', { method: 'POST' })
          ;[catalog, connectionRows] = await Promise.all([api<Model[]>('/api/models'), api<Provider[]>('/api/providers')])
          if (active) setNotice(catalog.length ? 'Model catalog loaded. Choose questions, then select Model A and Model B.' : 'No model catalog is available. Check provider credentials in Settings, then refresh the catalog in step 2.')
        }
        let rows = data
        let sample = rows.find(row => row.name === 'LLM Comparison Lab Original Demo')
        if (!sample) {
          await api('/api/datasets/built-in', { method: 'POST' })
          rows = await api<Dataset[]>('/api/datasets')
          sample = rows.find(row => row.name === 'LLM Comparison Lab Original Demo')
        }
        if (active) {
          setDatasets(rows); setModels(catalog); setProviders(connectionRows); setDrafts(saved)
          const sampleVersion = sample?.versions.find(row => row.version === 'v1')
          if (sample && sampleVersion) { setDatasetId(String(sample.id)); setVersion(sampleVersion.version); setVersionId(String(sampleVersion.id)) }
        }
      })
      .catch((cause: Error) => { if (active) setError(cause.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    const nonDraft = drafts.filter(draft => draft.status !== 'draft')
    if (!nonDraft.length) return
    let active = true
    void Promise.all(nonDraft.map(async draft => {
      try {
        const current = await api<Progress>(`/api/experiments/${draft.id}/progress`)
        if (!active) return
        setProgress(rows => ({ ...rows, [draft.id]: current }))
        if (!['queued', 'running'].includes(current.status)) {
          const report = await api<Results>(`/api/experiments/${draft.id}/results`)
          if (active) setResults(rows => ({ ...rows, [draft.id]: report }))
        }
      } catch (cause) { if (active) setRunErrors(rows => ({ ...rows, [draft.id]: (cause as Error).message })) }
    }))
    return () => { active = false }
  }, [drafts.map(draft => `${draft.id}:${draft.status}`).join(',')])

  useEffect(() => {
    const activeIds = drafts.filter(draft => ['queued', 'running'].includes(progress[draft.id]?.status ?? draft.status)).map(draft => draft.id)
    if (!activeIds.length) return
    let active = true
    const refresh = async () => { await Promise.all(activeIds.map(async id => {
      try {
        const current = await api<Progress>(`/api/experiments/${id}/progress`)
        if (!active) return
        setProgress(rows => ({ ...rows, [id]: current }))
        if (!['queued', 'running'].includes(current.status)) {
          setDrafts(rows => rows.map(draft => draft.id === id ? { ...draft, status: current.status, pause_reason: current.pause_reason } : draft))
          try { const report = await api<Results>(`/api/experiments/${id}/results`); if (active) setResults(rows => ({ ...rows, [id]: report })) }
          catch (cause) { if (active) setRunErrors(rows => ({ ...rows, [id]: (cause as Error).message })) }
        }
      } catch (cause) { if (active) setRunErrors(rows => ({ ...rows, [id]: (cause as Error).message })) }
    })) }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 2000)
    return () => { active = false; window.clearInterval(timer) }
  }, [drafts.map(draft => `${draft.id}:${progress[draft.id]?.status ?? draft.status}`).join(',')])

  useEffect(() => {
    setDetail(null); setEstimate(null)
    if (!datasetId || !version) return
    let active = true
    setDetailLoading(true)
    api<Version>(`/api/datasets/${datasetId}/versions/${encodeURIComponent(version)}`)
      .then(result => { if (active) { setDetail(result); setError('') } })
      .catch((cause: Error) => { if (active) setError(`Could not load dataset version: ${cause.message}`) })
      .finally(() => { if (active) setDetailLoading(false) })
    return () => { active = false }
  }, [datasetId, version])

  useEffect(() => { stepHeading.current?.focus() }, [step])

  const selectedDataset = datasets.find(row => String(row.id) === datasetId)
  const selectedModels = [models.find(model => String(model.id) === modelA), models.find(model => String(model.id) === modelB)].filter((model): model is Model => !!model)
  const providerNames = [...new Set([...models.map(model => model.provider), 'openrouter', 'opencode_zen', ...(mode === 'demo' ? ['fixture'] : [])])]
  const visibleModels = models.filter(model => (providerFilter === 'all' || model.provider === providerFilter) && `${model.name} ${model.model_id} ${model.provider}`.toLowerCase().includes(modelSearch.toLowerCase()))
  const duplicateRoute = selectedModels.length === 2 && selectedModels[0].provider === selectedModels[1].provider && selectedModels[0].model_id === selectedModels[1].model_id
  const temperatureSupported = selectedModels.length === 2 && selectedModels.every(model => model.supported_parameters.includes('temperature'))
  const selectionsCurrent = ![modelA, modelB].some(id => staleRouteIds.includes(id))
  const readyToReview = !!detail && !!versionId && selectedModels.length === 2 && !duplicateRoute && selectionsCurrent
  const explicitItemIds = selectedDataset?.name.match(/^LLM Comparison Lab Starter (5|10|20)$/) ? detail?.items.map(item => item.id) ?? null : null
  const currentDesignKey = JSON.stringify({ name, dataset_version_id: Number(versionId), model_snapshot_ids: [Number(modelA), Number(modelB)], item_ids: explicitItemIds, system_prompt: systemPrompt, max_tokens: maxTokens, temperature: temperature === '' || !temperatureSupported ? null : Number(temperature), repetitions, seed, timeout_seconds: timeout, retries_per_job: retries, attempt_cap: attemptCap })

  useEffect(() => {
    if (step !== 3) return
    if (!readyToReview || selectedModels.length !== 2) { setEstimate(null); setEstimateKey(''); setEstimateBusy(false); return }
    let active = true
    setEstimate(null); setEstimateKey(''); setEstimateError(''); setEstimateBusy(true)
    const timer = window.setTimeout(() => {
      void api<Estimate>('/api/experiments/estimate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: currentDesignKey })
        .then(result => { if (active) { setEstimate(result); setEstimateKey(currentDesignKey) } })
        .catch((cause: Error) => { if (active) setEstimateError(cause.message) })
        .finally(() => { if (active) setEstimateBusy(false) })
    }, 250)
    return () => { active = false; window.clearTimeout(timer) }
  }, [step, readyToReview, currentDesignKey])

  function design() {
    return { name, dataset_version_id: Number(versionId), model_snapshot_ids: [Number(modelA), Number(modelB)], item_ids: explicitItemIds,
      system_prompt: systemPrompt, max_tokens: maxTokens, temperature: temperature === '' || !temperatureSupported ? null : Number(temperature),
      repetitions, seed, timeout_seconds: timeout, retries_per_job: retries, attempt_cap: attemptCap }
  }

  async function startComparison() {
    if (startedDraftId !== null || startLock.current || busy || estimateBusy || !estimate?.ready || estimateKey !== JSON.stringify(design())) return
    startLock.current = true; setBusy(true); setError(''); setNotice('')
    let draftId = pendingDraftId
    try {
      if (draftId === null) {
        const saved = await api<Draft>('/api/experiments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(design()) })
        draftId = saved.id
        setPendingDraftId(saved.id); setExpandedDraftId(saved.id); setDrafts(rows => [saved, ...rows.filter(row => row.id !== saved.id)])
      }
      const started = await api<Draft>(`/api/experiments/${draftId}/start`, { method: 'POST' })
      setDrafts(rows => rows.map(row => row.id === draftId ? started : row))
      setStartedDraftId(draftId); setPendingDraftId(null); setNotice(`Comparison ${draftId} started.`)
      try { const current = await api<Progress>(`/api/experiments/${draftId}/progress`); setProgress(rows => ({ ...rows, [draftId!]: current })) }
      catch (cause) { setRunErrors(rows => ({ ...rows, [draftId!]: `Started, but progress could not be loaded: ${(cause as Error).message}` })) }
    } catch (cause) {
      setError(`${draftId !== null ? `Start status for draft ${draftId} is unconfirmed. It remains saved; check its history status before retrying to avoid a duplicate run. ` : ''}${(cause as Error).message}`)
      if (draftId !== null) setPendingDraftId(draftId)
    } finally { startLock.current = false; setBusy(false) }
  }

  async function saveDraft(event: FormEvent) {
    event.preventDefault()
    if (busy || startLock.current) return
    if (pendingDraftId !== null || startedDraftId !== null) { setNotice(`Comparison draft ${pendingDraftId ?? startedDraftId} already exists. Choose “New comparison” to create another.`); return }
    setBusy(true); setError(''); setNotice('')
    try {
      const saved = await api<Draft>('/api/experiments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(design()) })
      setDrafts(rows => [saved, ...rows.filter(row => row.id !== saved.id)]); setExpandedDraftId(saved.id); setPendingDraftId(saved.id); setNotice(`Draft ${saved.id} saved. Backend start-time checks are authoritative.`); setStep(3)
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  async function lifecycle(draft: Draft, action: 'start' | 'pause' | 'resume' | 'cancel') {
    if (runBusy !== null || (action === 'start' && startLock.current)) return
    setRunBusy(draft.id); setRunErrors(rows => ({ ...rows, [draft.id]: '' })); setNotice('')
    try {
      let url = `/api/experiments/${draft.id}/${action}`
      if (action === 'resume' && !window.confirm('The service may retry requests with uncertain remote outcomes. A provider may already have processed them. Resume and acknowledge this uncertainty?')) return
      if (action === 'resume') url += '?acknowledge_uncertain=true'
      if (action === 'start') startLock.current = true
      const updated = await api<Draft>(url, { method: 'POST' })
      setDrafts(rows => rows.map(row => row.id === draft.id ? updated : row))
      if (action === 'start' && pendingDraftId === draft.id) { setPendingDraftId(null); setStartedDraftId(draft.id) }
      const current = await api<Progress>(`/api/experiments/${draft.id}/progress`)
      setProgress(rows => ({ ...rows, [draft.id]: current }))
    } catch (cause) { setRunErrors(rows => ({ ...rows, [draft.id]: (cause as Error).message })) }
    finally { if (action === 'start') startLock.current = false; setRunBusy(null) }
  }

  async function installSample() {
    setBusy(true); setError(''); setNotice('')
    try {
      await api('/api/datasets/built-in', { method: 'POST' })
      const rows = await api<Dataset[]>('/api/datasets')
      setDatasets(rows)
      const sample = rows.find(row => row.name === 'LLM Comparison Lab Original Demo')
      const sampleVersion = sample?.versions.find(row => row.version === 'v1')
      if (sample && sampleVersion) { setDatasetId(String(sample.id)); setVersion(sampleVersion.version); setVersionId(String(sampleVersion.id)); setNotice('Original authored demonstration sample installed. It is not an established benchmark.') }
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  const statusReason = (model: Model) => model.provider === 'fixture' ? 'Synthetic fixture; demo mode only.' : !model.credential_configured ? 'Provider credential is not configured. Add it in Settings.' : model.availability !== 'available' ? `Currently ${model.availability}. Refresh the catalog to check again.` : !model.eligibility?.allowed ? `${policyHelp[model.eligibility?.reason] ?? 'This route is not eligible. Refresh the catalog for current evidence.'} (${model.eligibility?.reason ?? 'unknown'})` : !model.eligibility.checked_at || model.eligibility.model_id !== model.model_id || !model.pricing_source ? 'Matching fresh verified price evidence is missing. Refresh Models.' : 'Verified free at last check, not a permanent pricing guarantee. Configured credentials do not prove authenticated generation works.'
  const pauseMessage = (reason: string) => ({ rate_limit: 'The provider rate limit was reached. Wait for the cooldown, then resume.', authentication: 'Provider authentication failed. Check provider credentials in Settings before resuming.', auth: 'Provider authentication failed. Check provider credentials in Settings before resuming.', credentials: 'Provider authentication failed. Check provider credentials in Settings before resuming.', quota: 'The provider quota appears exhausted or unavailable. Check account limits before resuming.', quota_exhausted: 'The provider quota appears exhausted. Check account limits before resuming.', timeout: 'A request timed out. Its remote outcome may be unknown; resume requires acknowledgement.', stale_pricing: 'The verified-free pricing evidence expired. Refresh the catalog before resuming.', stale_pricing_or_route: 'The verified-free price evidence or exact route is no longer current. Refresh the catalog and reselect before resuming.', unknown_outcome: 'A provider may have received a request without a confirmed response. Resume requires acknowledgement because retrying can duplicate work.', unknown_remote_outcome: 'A provider may have received a request without a confirmed response. Resume requires acknowledgement because retrying can duplicate work.', execution_mode_mismatch: 'This comparison was created in a different execution mode. Return to the matching mode/database.', experiment_cap: 'The absolute attempt cap was reached. Create a new comparison with a higher cap if appropriate.', manual_cap: 'The manual attempt limit was reached.', fixture_demo_only: 'Fixture routes only run in demonstration mode.', demo_fixture_required: 'This demonstration run requires fixture models.', user: 'Paused by the user.' } as Record<string, string>)[reason] ?? reason.replaceAll('_', ' ')
  const optionDisabled = (model: Model, other: string) => !eligible(model, mode) || (other !== '' && models.find(row => String(row.id) === other)?.provider === model.provider && models.find(row => String(row.id) === other)?.model_id === model.model_id)
  const providerLabel = (slug: string) => slug === 'openrouter' ? 'OpenRouter' : slug === 'opencode_zen' ? 'OpenCode Zen' : slug === 'fixture' ? 'Demonstration fixtures' : slug
  const selectedRoute = (id: string) => models.find(model => String(model.id) === id)
  const routeSelector = (label: string, value: string, other: string, onChange: (value: string) => void) => {
    const selected = selectedRoute(value)
    const options = visibleModels.filter(model => showUnavailable || eligible(model, mode))
    if (selected && !options.some(model => model.id === selected.id)) options.unshift(selected)
    return <label className="block min-w-0">{label}<select aria-label={label} disabled={busy} className="mt-1 block w-full rounded border p-2" value={value} onChange={event => onChange(event.target.value)}><option value="">Choose a model</option>{options.map(model => <option key={model.id} value={model.id} disabled={optionDisabled(model, other) || staleRouteIds.includes(String(model.id))}>{model.name} — {providerLabel(model.provider)}{staleRouteIds.includes(String(model.id)) ? ' · needs reselect' : eligible(model, mode) ? ' · ready at last check' : ` · unavailable: ${statusReason(model)}`}</option>)}</select></label>
  }

  return <section aria-labelledby="experiments-heading" className="space-y-5">
    <h2 id="experiments-heading" className="text-xl font-semibold">Guided comparison</h2>
    <p>Set up a small comparison in three steps. Readiness is advisory; the backend is authoritative at start time.</p>
    {mode === 'demo' && <p role="status" className="rounded bg-amber-100 p-3 font-semibold text-amber-950">DEMONSTRATION MODE — synthetic fixture answers only. This does not measure real models or establish benchmark performance.</p>}
    {mode !== 'demo' && <p role="status" className="rounded bg-amber-50 p-3">LIVE MODE — starting a comparison can send requests to providers. Only select routes with backend-verified free evidence and configured credentials.</p>}
    {loading && <p role="status">Loading datasets, models, providers and saved comparisons…</p>}
    {error && <p role="alert" className="whitespace-pre-wrap text-red-800">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!loading && <>
      <nav aria-label="Comparison steps" className="grid gap-2 sm:grid-cols-3">{['Questions', 'Models', 'Review and start'].map((title, index) => <button key={title} type="button" disabled={pendingDraftId !== null || startedDraftId !== null} aria-current={step === index + 1 ? 'step' : undefined} onClick={() => { setStep(index + 1); setError('') }} className={`rounded border p-3 text-left disabled:opacity-60 ${step === index + 1 ? 'border-slate-900 bg-slate-100 font-semibold' : ''}`}><span className="block text-sm">Step {index + 1}</span>{title}</button>)}</nav>
      <div className="space-y-4 border-t pt-4">
        {step === 1 && <div className="space-y-4"><h3 ref={stepHeading} tabIndex={-1} className="text-lg font-semibold">1. Choose questions</h3>{pendingDraftId !== null && <p role="status">Draft {pendingDraftId} is saved. Its dataset and configuration are frozen; start it in Review or choose New comparison.</p>}
          <fieldset className="space-y-2"><legend className="font-semibold">Question source</legend><label className="block"><input type="radio" name="question-source" checked={questionChoice === 'sample'} onChange={() => { setQuestionChoice('sample'); void installSample() }} /> Try sample questions (default)</label><label className="block"><input type="radio" name="question-source" checked={questionChoice === 'own'} onChange={() => setQuestionChoice('own')} /> Use my own questions</label></fieldset>
          {questionChoice === 'sample' && <><p>The built-in authored sample is for demonstration and practice, not an established benchmark.</p><button type="button" onClick={() => void installSample()} disabled={busy} className="rounded border px-3 py-2 disabled:opacity-50">{busy ? 'Installing…' : 'Install and select sample questions'}</button></>}
          {questionChoice === 'own' && <><p>Import questions or install a starter set on the <Link to="/datasets" className="underline">Datasets tab</Link>, then select its saved version here.</p><Datasets compact onImported={(rows, importedId, importedVersion) => { setDatasets(rows); setDatasetId(String(importedId)); setVersion(importedVersion); const entry = rows.find(row => row.id === importedId)?.versions.find(row => row.version === importedVersion); setVersionId(entry ? String(entry.id) : ''); setNotice('Imported questions selected in this comparison.') }} /></>}
          <label className="block">Dataset <select className="mt-1 block w-full rounded border p-2" value={datasetId} onChange={event => { setDatasetId(event.target.value); setVersion(''); setVersionId('') }}><option value="">Choose an imported dataset</option>{datasets.map(row => <option key={row.id} value={row.id}>{row.name} — {row.origin} · {row.license}</option>)}</select></label>
          <label className="block">Version <select className="mt-1 block w-full rounded border p-2" value={version} onChange={event => { const choice = selectedDataset?.versions.find(item => item.version === event.target.value); setVersion(event.target.value); setVersionId(choice ? String(choice.id) : '') }}><option value="">Choose version</option>{selectedDataset?.versions.map(item => <option key={item.id} value={item.version}>{item.version} (version ID {item.id})</option>)}</select></label>
          {detailLoading && <p role="status">Loading question preview…</p>}
            {detail && <div className="space-y-2 rounded border p-3"><p><strong>Quick comparison selection:</strong> {detail.items.length} questions in this version; {explicitItemIds ? `all ${explicitItemIds.length} starter-set questions will be compared.` : `this comparison will use ${Math.min(10, detail.items.length)} category-balanced questions selected with the local seed.`}</p><p>Categories: {Object.entries(detail.category_inventory).map(([category, count]) => `${category}: ${count}`).join(', ') || 'none'}</p><details><summary><span className="cursor-pointer">Quick preview of question IDs and split metadata</span></summary><p>{detail.items.map(item => `${item.id}: ${item.split}, ${item.family_id ? `family ${item.family_id}` : 'no family'}, ${item.review_status}`).join(' · ')}</p></details></div>}
          <div className="flex justify-end"><button type="button" disabled={!detail || detailLoading} onClick={() => { setStep(2); setError('') }} className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-50">Continue to models</button></div>
        </div>}

        {step === 2 && <div className="space-y-4"><h3 ref={stepHeading} tabIndex={-1} className="text-lg font-semibold">2. Choose two models</h3>
          <p>Both models receive the same questions and shared instruction. The same model through different providers is allowed: provider routing can affect results. Your selections stay unchanged when filters change.</p>
           <p><strong>{visibleModels.filter(model => eligible(model, mode)).length} models ready to select</strong> under the current filter. Availability is not a guarantee that generation will succeed.</p>
           {(mode === 'demo' ? ['fixture'] : ['openrouter', 'opencode_zen']).map(provider => {
             const providerModels = visibleModels.filter(model => model.provider === provider && eligible(model, mode))
             const title = mode === 'demo' ? 'Synthetic demonstration models' : `${providerLabel(provider)} models`
             return <details key={provider} className="rounded border p-3"><summary className="cursor-pointer font-semibold">{title} ({providerModels.length} under current filters)</summary>
               {providerModels.length ? <ul className="mt-2 space-y-2">{providerModels.map(model => <li key={model.id}><details className="rounded border p-2"><summary className="cursor-pointer">{model.name} — {providerLabel(model.provider)}</summary><dl className="mt-2 break-all text-sm"><dt className="font-medium">Exact route</dt><dd>{model.provider} / {model.model_id}</dd><dt className="font-medium">Endpoint</dt><dd>{model.endpoint}</dd><dt className="font-medium">Availability</dt><dd>{model.availability}</dd><dt className="font-medium">Pricing evidence</dt><dd>{model.pricing_source ?? 'none'} · {model.eligibility.checked_at ?? 'never'}</dd><dt className="font-medium">Credential</dt><dd>{model.credential_configured ? 'configured' : 'not configured'}</dd></dl></details></li>)}</ul> : <p className="mt-2">{mode === 'demo' ? 'No synthetic demonstration routes match the current filters.' : 'No eligible routes match the current filters.'}</p>}
             </details>
           })}
          <label className="block"><input type="checkbox" checked={showUnavailable} onChange={event => setShowUnavailable(event.target.checked)} /> Show unavailable models and pricing restrictions</label>
          {mode === 'live' && providers.filter(provider => providerFilter === 'all' || provider.slug === providerFilter).map(provider => !provider.credential_configured ? <p key={provider.slug}>{providerLabel(provider.slug)}: credential missing. <Link to="/settings" className="underline">Open Settings for setup instructions</Link>.</p> : provider.connection_status !== 'connected' && !models.some(model => model.provider === provider.slug) ? <p key={provider.slug}>{providerLabel(provider.slug)}: catalog unavailable or not loaded. Refresh the provider catalog below; if it fails, check your connection and provider status.</p> : null)}
          <div className="grid gap-3 sm:grid-cols-2"><label>Provider filter<select className="mt-1 block w-full rounded border p-2" value={providerFilter} onChange={event => setProviderFilter(event.target.value)}><option value="all">All providers</option>{providerNames.map(provider => { const status = providers.find(row => row.slug === provider); return <option key={provider} value={provider}>{providerLabel(provider)} — {status?.connection_status ?? 'status unknown'}{status && !status.credential_configured && provider !== 'fixture' ? ', credential missing' : ''}</option> })}</select></label><label>Search models<input className="mt-1 block w-full rounded border p-2" type="search" value={modelSearch} onChange={event => setModelSearch(event.target.value)} placeholder="Name, route ID or provider" /></label></div>
          <div className="grid gap-3 sm:grid-cols-2">{routeSelector('Model A', modelA, modelB, setModelA)}{routeSelector('Model B', modelB, modelA, setModelB)}</div>
          {([{ label: 'Model A', model: models.find(model => String(model.id) === modelA) }, { label: 'Model B', model: models.find(model => String(model.id) === modelB) }] as const).map(({ label, model }) => model && <article key={label} className="rounded border p-3"><h4 className="font-semibold">{label}: {model.name}</h4><p>{providerLabel(model.provider)} · {eligible(model, mode) ? 'Eligible at last check' : 'Unavailable for current execution'}</p>{staleRouteIds.includes(String(model.id)) && <p role="status">Catalog changed this route’s snapshot. Reselect the current option to continue.</p>}<details><summary className="cursor-pointer">Exact route and evidence</summary><p className="break-all">{model.provider} / {model.model_id}</p><p>Endpoint: {model.endpoint} · availability: {model.availability} · credential: {model.credential_configured ? 'configured' : 'not configured'}</p><p>Pricing evidence: {model.pricing_source ?? 'none'} · checked: {model.eligibility?.checked_at ?? 'never'}</p><p>{statusReason(model)}</p></details>{!model.credential_configured && model.provider !== 'fixture' && <Link className="underline" to="/settings">Configure credentials in Settings</Link>}</article>)}
          <div className="flex flex-wrap items-center justify-between gap-2"><button type="button" disabled={pendingDraftId !== null || startedDraftId !== null} onClick={() => { setStep(1); setError('') }} className="rounded border px-3 py-2 disabled:opacity-50">Back to questions</button><div className="flex flex-wrap gap-2"><button type="button" disabled={busy} onClick={() => void reloadCatalog()} className="rounded border px-3 py-2 disabled:opacity-50">{busy ? 'Refreshing…' : 'Refresh provider catalog'}</button><Link className="rounded border px-3 py-2" to="/models">Models and availability</Link><button type="button" disabled={!readyToReview || pendingDraftId !== null || startedDraftId !== null} onClick={() => { setStep(3); setError('') }} className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-50">Continue to review</button></div></div>
          <details><summary className="cursor-pointer">Why are some routes unavailable?</summary><ul className="list-inside list-disc">{visibleModels.filter(model => !eligible(model, mode)).map(model => <li key={model.id}><span className="break-all">{model.provider} / {model.model_id}</span>: {statusReason(model)}{!model.credential_configured && model.provider !== 'fixture' && <> <Link className="underline" to="/settings">Open Settings</Link></>}{model.provider !== 'fixture' && <> <button type="button" className="ml-1 underline" onClick={() => void reloadCatalog()}>Refresh catalog</button></>}</li>)}</ul>{visibleModels.length === 0 && <p>No catalog routes match the current filter.</p>}</details>
        </div>}

        {step === 3 && <form onSubmit={saveDraft} className="space-y-4"><h3 ref={stepHeading} tabIndex={-1} className="text-lg font-semibold">3. Review and start</h3>
          {pendingDraftId !== null && <p role="status">This is the saved configuration for draft {pendingDraftId}. Settings are locked so Start cannot run a different design than the one shown.</p>}
          <label className="block">Comparison name<input className="mt-1 block w-full rounded border p-2" value={name} onChange={event => setName(event.target.value)} maxLength={255} required disabled={pendingDraftId !== null || startedDraftId !== null} /></label>
          <p><strong>Questions:</strong> {selectedDataset?.name} / {version} · {estimate?.item_ids.length ?? (explicitItemIds?.length ?? Math.min(10, detail?.items.length ?? 0))} of {detail?.items.length ?? 0} selected{explicitItemIds ? ', all starter-set items' : ', category-balanced with the local seed'}. This authored sample is not a benchmark.</p><p><strong>Routes:</strong> {selectedModels.map(model => `${providerLabel(model.provider)} / ${model.model_id}`).join(' vs ') || 'Choose two routes in step 2'}.</p><p>Both models receive the same selected questions and shared instruction; provider route is the intended comparison difference.</p>
          <details className="rounded border p-3"><summary className="cursor-pointer font-semibold">Advanced settings</summary><div className="mt-3 space-y-3"><label className="block">Shared system instruction<textarea className="mt-1 block w-full rounded border p-2" value={systemPrompt} onChange={event => setSystemPrompt(event.target.value)} maxLength={20000} rows={3} disabled={pendingDraftId !== null || startedDraftId !== null} /></label><div className="grid gap-3 sm:grid-cols-2"><label>Max output tokens<input className="mt-1 block w-full rounded border p-2" type="number" min="1" max="4096" step="1" value={maxTokens} onChange={event => setMaxTokens(event.target.valueAsNumber)} required disabled={pendingDraftId !== null || startedDraftId !== null} /></label><label>Temperature (blank omits)<input className="mt-1 block w-full rounded border p-2" type="number" min="0" max="2" step="any" value={temperature} onChange={event => setTemperature(event.target.value)} disabled={!temperatureSupported || pendingDraftId !== null || startedDraftId !== null} /></label><label>Repetitions<input className="mt-1 block w-full rounded border p-2" type="number" min="1" max="20" step="1" value={repetitions} onChange={event => setRepetitions(event.target.valueAsNumber)} required disabled={pendingDraftId !== null || startedDraftId !== null} /></label><label>Local sampling/order seed<input className="mt-1 block w-full rounded border p-2" type="number" step="1" value={seed} onChange={event => setSeed(event.target.valueAsNumber)} required disabled={pendingDraftId !== null || startedDraftId !== null} /></label><label>Request timeout (seconds)<input className="mt-1 block w-full rounded border p-2" type="number" min="1" max="300" step="1" value={timeout} onChange={event => setTimeout(event.target.valueAsNumber)} required disabled={pendingDraftId !== null || startedDraftId !== null} /></label><label>Retries per job (0 = none)<input className="mt-1 block w-full rounded border p-2" type="number" min="0" max="10" step="1" value={retries} onChange={event => setRetries(event.target.valueAsNumber)} required disabled={pendingDraftId !== null || startedDraftId !== null} /></label><label>Absolute generation attempt cap<input className="mt-1 block w-full rounded border p-2" type="number" min="1" max="100000" step="1" value={attemptCap} onChange={event => setAttemptCap(event.target.valueAsNumber)} required disabled={pendingDraftId !== null || startedDraftId !== null} /></label></div>{!temperatureSupported && <p className="text-sm">Temperature is disabled because both selected routes must support it. Its entered value is retained and will be omitted from the shared request until supported.</p>}<p className="text-sm">The local seed selects questions and their order; it does not make provider output deterministic. Requested settings must be supported by both routes.</p></div></details>
          {estimateBusy && <p role="status">Checking this design with the backend…</p>}{estimateError && <p role="alert" className="whitespace-pre-wrap text-red-800">Could not estimate this design: {estimateError}</p>}
          {estimate && estimateKey === currentDesignKey && <div role="status" className="space-y-2 rounded border p-3">
            <h4 className="font-semibold">Backend request estimate (advisory)</h4>
            <p>Questions selected: {estimate.item_ids.length} · repetitions: {repetitions} · initial generation requests: {estimate.estimate.initial_candidate_requests} · maximum candidate retries: {estimate.estimate.maximum_candidate_retries}.</p>
            <p>Absolute attempt cap: {attemptCap}. At most {estimate.estimate.maximum_attempts} attempts are planned under this retry policy (uncapped maximum {estimate.estimate.unconstrained_maximum_attempts}). Uncertain outcomes are never silently retried.</p>
            <p>{mode === 'demo' ? 'Synthetic answers only; no provider generation calls or real charges.' : 'Verified-free status relies on current pricing evidence, not a permanent guarantee. The backend checks again before dispatch.'}</p>
            <details><summary>Readiness and metadata requests</summary><p>Provider metadata checks: {estimate.estimate.metadata_startup} at startup and up to {estimate.estimate.metadata_refresh} refresh checks. This is not quota assurance.</p><p>Readiness: {estimate.ready ? 'eligible at estimate time; backend checks again when started' : 'blocked; saving a draft is still possible'}.</p><ul>{estimate.policy_decisions_advisory.map((decision, index) => <li key={index}>{providerLabel(decision.provider)} / {decision.model_id}: {decision.allowed ? 'eligible' : `blocked — ${decision.reason}`}</li>)}</ul></details>
          </div>}
          <div className="flex flex-wrap justify-between gap-2">
            <button type="button" disabled={pendingDraftId !== null || startedDraftId !== null} onClick={() => setStep(2)} className="rounded border px-3 py-2 disabled:opacity-50">Back to models</button>
            <div className="flex flex-wrap gap-2">
              <button type="submit" disabled={busy || !readyToReview || pendingDraftId !== null || startedDraftId !== null} className="rounded border px-3 py-2 disabled:opacity-50">Save draft</button>
              {(startedDraftId !== null || pendingDraftId !== null) && <><span role="status" className="self-center">{startedDraftId !== null ? `Comparison ${startedDraftId} has started.` : `Draft ${pendingDraftId} is saved.`}</span><button type="button" disabled={busy} onClick={() => { setStartedDraftId(null); setPendingDraftId(null); setName(`${name} (new)`); setEstimate(null); setStep(1) }} className="rounded border px-3 py-2">New comparison</button></>}
              {startedDraftId === null && <button type="button" disabled={busy || estimateBusy || !readyToReview || !estimate?.ready || estimateKey !== currentDesignKey} onClick={event => { if (event.currentTarget.form?.reportValidity()) void startComparison() }} className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-50">{busy ? 'Starting…' : pendingDraftId !== null ? 'Start saved draft' : 'Start comparison'}</button>}
            </div>
          </div>
        </form>}
      </div>

      <section aria-labelledby="saved-heading" className="border-t pt-4"><h3 id="saved-heading" className="font-semibold">Saved comparisons and history</h3>
        {drafts.length === 0 ? <p>No saved comparisons yet.</p> : <ul className="space-y-2">{drafts.map(draft => {
          const expanded = expandedDraftId === draft.id; const detailsId = `saved-draft-details-${draft.id}`; const currentStatus = progress[draft.id]?.status ?? draft.status
          return <li key={draft.id} className="rounded border p-3"><button type="button" className="flex w-full flex-wrap items-center justify-between gap-2 text-left" aria-expanded={expanded} aria-controls={detailsId} onClick={() => setExpandedDraftId(expanded ? null : draft.id)}><span><strong>{draft.name}</strong> (ID {draft.id}; {currentStatus}; {draft.provenance_mode}) · {draft.config.item_ids.length} questions · {draft.estimate.initial_candidate_requests} initial requests</span><span className="underline">{expanded ? 'Collapse' : 'Expand'}</span></button>
            <div id={detailsId} hidden={!expanded}><p className="mt-2">Dataset version ID {draft.dataset_version_id} · exact routes: {draft.config.models.map(model => `${model.provider} / ${model.model_id}`).join(' vs ')} · backend readiness is advisory.</p><div className="mt-2 flex flex-wrap gap-2">{currentStatus === 'draft' && <button type="button" disabled={runBusy !== null} onClick={() => void lifecycle(draft, 'start')} className="rounded border px-3 py-1 disabled:opacity-50">Start</button>}{['queued', 'running'].includes(currentStatus) && <><button type="button" disabled={runBusy !== null} onClick={() => void lifecycle(draft, 'pause')} className="rounded border px-3 py-1 disabled:opacity-50">Pause</button><button type="button" disabled={runBusy !== null} onClick={() => void lifecycle(draft, 'cancel')} className="rounded border px-3 py-1 disabled:opacity-50">Cancel</button></>}{['paused', 'interrupted'].includes(currentStatus) && <><button type="button" disabled={runBusy !== null} onClick={() => void lifecycle(draft, 'resume')} className="rounded border px-3 py-1 disabled:opacity-50">Resume</button><button type="button" disabled={runBusy !== null} onClick={() => void lifecycle(draft, 'cancel')} className="rounded border px-3 py-1 disabled:opacity-50">Cancel</button></>}</div>
              <p className="mt-2 text-sm">Pause stops new work and preserves logs; already-dispatched requests may finish. Resume may retry requests whose remote outcome is unknown, so it asks for acknowledgement. Cancel stops remaining work; saved attempt and response logs remain in history.</p>
              {runErrors[draft.id] && <p role="alert" className="mt-2 whitespace-pre-wrap text-red-800">Comparison {draft.id}: {runErrors[draft.id]}</p>}
              {progress[draft.id] && <div className="mt-2" aria-label={`Progress for comparison ${draft.id}`}><p>{progress[draft.id].questions_completed != null && progress[draft.id].questions_total != null && <>Questions with all answers: {progress[draft.id].questions_completed} of {progress[draft.id].questions_total} · </>}{progress[draft.id].completed} successful requests · {progress[draft.id].failed} failed · {progress[draft.id].pending} pending · {progress[draft.id].in_flight} active · {progress[draft.id].cancelled} cancelled · attempts {progress[draft.id].attempts_consumed} consumed / {progress[draft.id].attempts_remaining} remaining</p>{progress[draft.id].pause_reason && <div><p>Paused: {pauseMessage(progress[draft.id].pause_reason ?? '')} Completed answers have been saved.</p><details><summary className="cursor-pointer">Technical pause reason</summary><code>{progress[draft.id].pause_reason}</code></details></div>}</div>}
              {expanded && results[draft.id] && <ResultsPanel experimentId={draft.id} report={results[draft.id]} />}
            </div></li>
        })}</ul>}
      </section>
    </>}
  </section>
}
