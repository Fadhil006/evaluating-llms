import { useEffect, useState, type FormEvent } from 'react'
import { api, type Dataset } from './Datasets'
import ResultsPanel, { type DashboardReport } from './ResultsPanel'

type Model = { id: number; provider: string; model_id: string; name: string; availability: string; credential_configured: boolean; pricing_source: string | null; supported_parameters: string[]; eligibility: { allowed: boolean; reason: string; checked_at: string | null; model_id: string } }
type Version = { dataset_id: number; version: string; category_inventory: Record<string, number>; items: { id: string; task_type: string }[] }
type Budget = { initial_candidate_requests: number; maximum_candidate_retries: number; unconstrained_maximum_attempts: number; maximum_attempts: number; metadata_startup: number; metadata_refresh: number }
type Estimate = { estimate: Budget; item_ids: string[]; category_counts: Record<string, number>; ready: boolean; policy_decisions_advisory: { provider: string; model_id: string; allowed: boolean; reason: string }[] }
type Draft = { id: number; name: string; status: string; pause_reason?: string | null; provenance_mode: string; dataset_version_id: number; estimate: Budget; ready: boolean; config: { item_ids: string[]; attempt_cap: number; models: { provider: string; model_id: string }[] } }
type Progress = { status: string; pause_reason: string | null; completed: number; failed: number; pending: number; in_flight: number; cancelled: number; attempts_consumed: number; attempts_remaining: number }
type Results = DashboardReport

const eligible = (model: Model) => model.eligibility?.allowed === true && model.credential_configured && !!model.eligibility.checked_at && model.eligibility.model_id === model.model_id && !!model.pricing_source

export default function Experiments({ mode }: { mode?: 'live' | 'demo' }) {
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [models, setModels] = useState<Model[]>([])
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
  const [datasetId, setDatasetId] = useState('')
  const [version, setVersion] = useState('')
  const [versionId, setVersionId] = useState('')
  const [detail, setDetail] = useState<Version | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [selectedModels, setSelectedModels] = useState<number[]>([])
  const [name, setName] = useState('')
  const [selection, setSelection] = useState<'quick' | 'explicit'>('quick')
  const [itemIds, setItemIds] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [maxTokens, setMaxTokens] = useState(512)
  const [temperature, setTemperature] = useState('')
  const [repetitions, setRepetitions] = useState(1)
  const [seed, setSeed] = useState(42)
  const [timeout, setTimeout] = useState(60)
  const [retries, setRetries] = useState(2)
  const [attemptCap, setAttemptCap] = useState(40)
  const [estimate, setEstimate] = useState<Estimate | null>(null)

  useEffect(() => {
    const nonDraft = drafts.filter(draft => draft.status !== 'draft')
    if (nonDraft.length) {
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
    }
  }, [drafts.map(draft => `${draft.id}:${draft.status}`).join(',')])

  useEffect(() => {
    let active = true
    Promise.all([api<Dataset[]>('/api/datasets'), api<Model[]>('/api/models'), api<Draft[]>('/api/experiments')])
      .then(([data, catalog, saved]) => { if (active) { setDatasets(data); setModels(catalog); setDrafts(saved) } })
      .catch((cause: Error) => { if (active) setError(cause.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    const activeIds = drafts.filter(draft => ['queued', 'running'].includes(progress[draft.id]?.status ?? draft.status)).map(draft => draft.id)
    if (!activeIds.length) return
    let active = true
    const refresh = async () => {
      await Promise.all(activeIds.map(async id => {
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
      }))
    }
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

  const selectedDataset = datasets.find(row => String(row.id) === datasetId)
  const selectableModels = mode === 'demo' ? models.filter(model => model.provider === 'fixture') : models.filter(eligible)
  const available = selectableModels.length
  const selected = selectedModels.map(id => models.find(model => model.id === id)).filter((model): model is Model => !!model)

  function design() {
    return {
      name, dataset_version_id: Number(versionId), model_snapshot_ids: selectedModels,
      item_ids: selection === 'quick' ? null : itemIds.split(/[\s,]+/).filter(Boolean),
      system_prompt: systemPrompt, max_tokens: maxTokens,
      temperature: temperature === '' ? null : Number(temperature), repetitions, seed,
      timeout_seconds: timeout, retries_per_job: retries, attempt_cap: attemptCap,
    }
  }

  async function submit(event: FormEvent, save: boolean) {
    event.preventDefault()
    setBusy(true); setError(''); setNotice(''); setEstimate(null)
    try {
      const payload = JSON.stringify(design())
      const result = await api<Estimate | Draft>(save ? '/api/experiments' : '/api/experiments/estimate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: payload,
      })
      if (save) {
        const saved = result as Draft
        setDrafts(await api<Draft[]>('/api/experiments'))
        setExpandedDraftId(saved.id)
        setNotice(`Draft ${saved.id} saved. Readiness is advisory; backend start-time checks remain authoritative.`)
      } else setEstimate(result as Estimate)
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  async function lifecycle(draft: Draft, action: 'start' | 'pause' | 'resume' | 'cancel') {
    setRunBusy(draft.id); setRunErrors(rows => ({ ...rows, [draft.id]: '' })); setNotice('')
    try {
      let url = `/api/experiments/${draft.id}/${action}`
      if (action === 'resume' && !window.confirm('This experiment may retry requests with an uncertain remote outcome. A provider may already have processed them and charged quota. Resume anyway?')) return
      if (action === 'resume') url += '?acknowledge_uncertain=true'
      const updated = await api<Draft>(url, { method: 'POST' })
      setDrafts(rows => rows.map(row => row.id === draft.id ? updated : row))
      const current = await api<Progress>(`/api/experiments/${draft.id}/progress`)
      setProgress(rows => ({ ...rows, [draft.id]: current }))
      if (!['queued', 'running'].includes(current.status)) {
        const report = await api<Results>(`/api/experiments/${draft.id}/results`)
        setResults(rows => ({ ...rows, [draft.id]: report }))
      }
    } catch (cause) { setRunErrors(rows => ({ ...rows, [draft.id]: (cause as Error).message })) }
    finally { setRunBusy(null) }
  }

  return <section aria-labelledby="experiments-heading" className="space-y-5">
    <h2 id="experiments-heading" className="text-xl font-semibold">Experiments</h2>
    <p>Design, run and inspect comparisons. Readiness shown here is advisory; the backend is authoritative and may reject a start.</p>
    {loading && <p role="status">Loading datasets, models and drafts…</p>}
    {error && <p role="alert" className="whitespace-pre-wrap text-red-800">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!loading && <>
      <p role="status">{mode === 'demo' ? `${available} synthetic fixture route(s) available locally. Any output is demonstration data, not a real model evaluation.` : available < 2 ? `Only ${available} backend-eligible route(s) at last check; live comparison is blocked. You may save a draft with two distinct catalog routes.` : `${available} backend-eligible route(s) at last check. Start-time checks are still required.`}</p>
      <form className="space-y-4 border-t pt-4" onSubmit={event => submit(event, (event.nativeEvent as SubmitEvent).submitter?.getAttribute('value') === 'save')} onChange={() => setEstimate(null)}>
        <h3 className="font-semibold">New draft</h3>
        <label className="block">Experiment name <input className="block w-full rounded border p-2" value={name} onChange={event => setName(event.target.value)} maxLength={255} required /></label>
        <label className="block">Dataset <select className="block w-full rounded border p-2" value={datasetId} onChange={event => { setDatasetId(event.target.value); setVersion(''); setVersionId('') }} required><option value="">Choose dataset</option>{datasets.map(row => <option key={row.id} value={row.id}>{row.name} (ID {row.id})</option>)}</select></label>
        <label className="block">Dataset version <select className="block w-full rounded border p-2" value={version} onChange={event => { const choice = selectedDataset?.versions.find(item => item.version === event.target.value); setVersion(event.target.value); setVersionId(choice ? String(choice.id) : ''); setItemIds('') }} required><option value="">Choose version</option>{selectedDataset?.versions.map(item => <option key={item.id} value={item.version}>{item.version} (ID {item.id})</option>)}</select></label>
        {detailLoading && <p role="status">Loading version items…</p>}
        {detail && <p>Version {detail.version}: {detail.items.length} items · {Object.entries(detail.category_inventory).map(([category, count]) => `${category}: ${count}`).join(', ')}. Item IDs: {detail.items.map(item => item.id).join(', ')}</p>}
        <fieldset className="space-y-2"><legend className="font-semibold">Exact model routes (select at least two distinct routes)</legend>
           {selectableModels.length === 0 ? <p>{mode === 'demo' ? 'No synthetic fixture routes. Refresh the Models page.' : `No current verified-free routes with configured credentials to select (${models.length} catalog entries were checked). Paid, unknown-price, unsupported, unavailable and unconfigured routes are not selectable.`}</p> : selectableModels.map(model => <label key={model.id} className="block rounded border p-2">
             <input type="checkbox" checked={selectedModels.includes(model.id)} onChange={event => setSelectedModels(ids => event.target.checked ? [...ids, model.id] : ids.filter(id => id !== model.id))} /> {model.name} — <span className="break-all">{model.provider} / {model.model_id}</span> (snapshot {model.id}) · {mode === 'demo' && model.provider === 'fixture' ? 'DEMONSTRATION synthetic fixture (demo only)' : eligible(model) ? 'Eligible at last check' : `Blocked for live use: ${model.eligibility?.reason ?? 'No decision'}${model.eligibility?.allowed && !eligible(model) ? '; matching dated evidence missing' : ''}`} · availability: {model.availability}
          </label>)}
        </fieldset>
        {selected.some(model => !model.supported_parameters.includes('max_tokens')) && <p className="text-amber-900">One or more selected routes do not support shared max tokens; the backend will reject this design.</p>}
        <fieldset><legend className="font-semibold">Item selection</legend>
          <label className="block"><input type="radio" name="items" checked={selection === 'quick'} onChange={() => setSelection('quick')} /> Quick: up to 10 category-balanced items, deterministic by seed</label>
          <label className="block"><input type="radio" name="items" checked={selection === 'explicit'} onChange={() => setSelection('explicit')} /> Explicit item IDs</label>
          {selection === 'explicit' && <label className="block">IDs (comma or whitespace separated, in desired order) <textarea className="block w-full rounded border p-2" value={itemIds} onChange={event => setItemIds(event.target.value)} required rows={3} /></label>}
        </fieldset>
        <label className="block">Shared system instruction <textarea className="block w-full rounded border p-2" value={systemPrompt} onChange={event => setSystemPrompt(event.target.value)} maxLength={20000} rows={3} /></label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label>Max output tokens <input className="block w-full rounded border p-2" type="number" min="1" max="4096" step="1" value={maxTokens} onChange={event => setMaxTokens(event.target.valueAsNumber)} required /></label>
          <label>Temperature (blank = omit for all routes) <input className="block w-full rounded border p-2" type="number" min="0" max="2" step="any" value={temperature} onChange={event => setTemperature(event.target.value)} /></label>
          <label>Repetitions <input className="block w-full rounded border p-2" type="number" min="1" max="20" step="1" value={repetitions} onChange={event => setRepetitions(event.target.valueAsNumber)} required /></label>
          <label>Local sampling/order seed <input className="block w-full rounded border p-2" type="number" step="1" value={seed} onChange={event => setSeed(event.target.valueAsNumber)} required /></label>
          <label>Timeout (seconds) <input className="block w-full rounded border p-2" type="number" min="1" max="300" step="1" value={timeout} onChange={event => setTimeout(event.target.valueAsNumber)} required /></label>
          <label>Retries per job <input className="block w-full rounded border p-2" type="number" min="0" max="10" step="1" value={retries} onChange={event => setRetries(event.target.valueAsNumber)} required /></label>
          <label>Absolute generation attempt cap <input className="block w-full rounded border p-2" type="number" min="1" max="100000" step="1" value={attemptCap} onChange={event => setAttemptCap(event.target.valueAsNumber)} required /></label>
        </div>
        <p className="text-sm">Seed selects local items and order; it does not guarantee deterministic provider output. Temperature requires support on every selected route.</p>
        <div className="flex flex-wrap gap-2"><button type="submit" value="estimate" disabled={busy || selectedModels.length < 2 || !detail} className="rounded border px-3 py-2 disabled:opacity-50">{busy ? 'Working…' : 'Estimate requests'}</button>
          <button type="submit" value="save" disabled={busy || selectedModels.length < 2 || !detail} className="rounded bg-slate-900 px-3 py-2 text-white disabled:opacity-50">Save draft</button></div>
      </form>
      {estimate && <div role="status" className="space-y-2 rounded border p-3"><h3 className="font-semibold">Backend estimate (advisory)</h3>
        <p>Initial generation requests: {estimate.estimate.initial_candidate_requests} · Maximum candidate retries within cap: {estimate.estimate.maximum_candidate_retries} · Maximum generation attempts: {estimate.estimate.maximum_attempts} (uncapped: {estimate.estimate.unconstrained_maximum_attempts}).</p>
        <p>Metadata checks (separate from generations): expected startup {estimate.estimate.metadata_startup}; possible refresh {estimate.estimate.metadata_refresh}.</p>
        <p>Selected item IDs: {estimate.item_ids.join(', ')} · Categories: {Object.entries(estimate.category_counts).map(([category, count]) => `${category}: ${count}`).join(', ')}</p>
        <p>Readiness at estimate time: {estimate.ready ? 'all selected routes eligible (advisory only)' : 'blocked for live execution (draft can still be saved)'}.</p>
        <ul className="list-inside list-disc">{estimate.policy_decisions_advisory.map((decision, index) => <li key={index}>{decision.provider} / {decision.model_id}: {decision.allowed ? 'eligible' : `blocked — ${decision.reason}`}</li>)}</ul>
      </div>}
       <div><h3 className="font-semibold">Saved drafts and experiments</h3>
         {drafts.length === 0 ? <p>No saved experiments yet.</p> : <ul className="space-y-2">{drafts.map(draft => {
           const expanded = expandedDraftId === draft.id
           const detailsId = `saved-draft-details-${draft.id}`
           const currentStatus = progress[draft.id]?.status ?? draft.status
           return <li key={draft.id} className="rounded border p-3">
             <button type="button" className="flex w-full flex-wrap items-center justify-between gap-2 text-left" aria-expanded={expanded} aria-controls={detailsId} onClick={() => setExpandedDraftId(expanded ? null : draft.id)}>
               <span><strong>{draft.name}</strong> (ID {draft.id}; {currentStatus}; {draft.provenance_mode}) · {draft.config.item_ids.length} items · {draft.estimate.initial_candidate_requests} initial requests</span>
               <span className="underline">{expanded ? 'Collapse experiment' : 'Expand experiment'}</span>
             </button>
             <div id={detailsId} hidden={!expanded}>
               <p className="mt-2">Dataset version ID {draft.dataset_version_id} · Routes: {draft.config.models.map(model => `${model.provider} / ${model.model_id}`).join(', ')} · readiness {draft.ready ? 'eligible when saved (advisory)' : 'blocked when saved (advisory)'}</p>
               <div className="mt-2 flex flex-wrap gap-2" aria-label={`Controls for ${draft.name}`}>
                 {currentStatus === 'draft' && <button type="button" disabled={runBusy !== null} onClick={() => void lifecycle(draft, 'start')} className="rounded border px-3 py-1 disabled:opacity-50">Start</button>}
                 {['queued', 'running'].includes(currentStatus) && <><button type="button" disabled={runBusy !== null} onClick={() => void lifecycle(draft, 'pause')} className="rounded border px-3 py-1 disabled:opacity-50">Pause</button><button type="button" disabled={runBusy !== null} onClick={() => void lifecycle(draft, 'cancel')} className="rounded border px-3 py-1 disabled:opacity-50">Cancel</button></>}
                 {['paused', 'interrupted'].includes(currentStatus) && <><button type="button" disabled={runBusy !== null} onClick={() => void lifecycle(draft, 'resume')} className="rounded border px-3 py-1 disabled:opacity-50">Resume</button><button type="button" disabled={runBusy !== null} onClick={() => void lifecycle(draft, 'cancel')} className="rounded border px-3 py-1 disabled:opacity-50">Cancel</button></>}
               </div>
               {runErrors[draft.id] && <p role="alert" className="mt-2 whitespace-pre-wrap text-red-800">Experiment {draft.id}: {runErrors[draft.id]}</p>}
               {progress[draft.id] && <div className="mt-2" aria-label={`Progress for experiment ${draft.id}`}>
                 <p>{progress[draft.id].completed} completed · {progress[draft.id].failed} failed · {progress[draft.id].pending} pending · {progress[draft.id].in_flight} in flight · {progress[draft.id].cancelled} cancelled · attempts {progress[draft.id].attempts_consumed} consumed / {progress[draft.id].attempts_remaining} remaining</p>
                 {progress[draft.id].pause_reason && <p>Pause reason: {progress[draft.id].pause_reason}</p>}
               </div>}
               {results[draft.id] && <ResultsPanel experimentId={draft.id} report={results[draft.id]} />}
             </div>
           </li>
         })}</ul>}
      </div>
    </>}
  </section>
}
