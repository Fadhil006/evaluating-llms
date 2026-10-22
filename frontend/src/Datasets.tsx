import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

export type Dataset = { id: number; name: string; description: string; origin: string; source: string; license: string; versions: { id: number; version: string }[] }
type Duplicate = { row: number; id: string; matches_row: number }
type Preview = { row_count: number; content_sha256: string; category_inventory: Record<string, number>; duplicate_content: Duplicate[] }
type VersionDetail = { version: string; content_sha256: string; category_inventory: Record<string, number>; manifest: Record<string, unknown>; items: { id: string; task_type: string; prompt: string; context: string | null; choices: string[] | null; reference_answers: unknown[]; scoring_config: Record<string, unknown>; tags: string[]; split: string; family_id: string | null; variant_id: string | null; source: string; license: string; review_status: string; provenance: Record<string, unknown> }[] }

export async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    let message = `Request failed (${response.status}).`
    try {
      const body = await response.json()
      const detail = body.detail
      if (Array.isArray(detail?.errors)) message = detail.errors.map((error: { row?: number; field?: string | string[]; loc?: (string | number)[]; message?: string; msg?: string }) =>
        `${error.row ? `Row ${error.row}, ` : ''}${Array.isArray(error.field) ? error.field.join('.') : error.field ?? error.loc?.join('.') ?? 'Input'}: ${error.message ?? error.msg ?? 'Invalid value'}`).join('\n')
      else if (Array.isArray(detail)) message = detail.map((error: { loc?: (string | number)[]; msg?: string }) => `${error.loc?.join('.') ?? 'Input'}: ${error.msg ?? 'Invalid value'}`).join('\n')
      else if (typeof detail === 'string') message = detail
    } catch { /* Keep HTTP status for non-JSON responses. */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export default function Datasets({ onImported, compact = false }: { onImported?: (datasets: Dataset[], datasetId: number, version: string) => void; compact?: boolean }) {
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [previewFile, setPreviewFile] = useState<File | null>(null)
  const [acknowledge, setAcknowledge] = useState(false)
  const [name, setName] = useState('')
  const [version, setVersion] = useState('v1')
  const [datasetId, setDatasetId] = useState('')
  const [description, setDescription] = useState('')
  const [source, setSource] = useState('')
  const [license, setLicense] = useState('')
  const [selectedVersion, setSelectedVersion] = useState('')
  const [detail, setDetail] = useState<VersionDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [starterBusy, setStarterBusy] = useState(false)

  useEffect(() => {
    let active = true
    api<Dataset[]>('/api/datasets').then(rows => { if (active) setDatasets(rows) })
      .catch((cause: Error) => { if (active) setError(cause.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (compact || !selectedVersion) { setDetail(null); setDetailLoading(false); return }
    const [id, ...versionParts] = selectedVersion.split(':')
    let active = true
    setDetail(null); setDetailLoading(true)
    api<VersionDetail>(`/api/datasets/${id}/versions/${encodeURIComponent(versionParts.join(':'))}`).then(value => { if (active) setDetail(value) })
      .catch((cause: Error) => { if (active) setError(cause.message) }).finally(() => { if (active) setDetailLoading(false) })
    return () => { active = false }
  }, [selectedVersion, compact])

  async function installStarters() {
    setStarterBusy(true); setError(''); setNotice('')
    try {
      const result = await api<{ datasets: { question_count: number; already_present: boolean }[] }>('/api/datasets/starter-sets', { method: 'POST' })
      setDatasets(await api<Dataset[]>('/api/datasets'))
      setNotice(`Starter sets ready: ${result.datasets.map(row => `${row.question_count} questions${row.already_present ? ' (already present)' : ''}`).join(', ')}.`)
    } catch (cause) { setError((cause as Error).message) }
    finally { setStarterBusy(false) }
  }

  async function install() {
    setBusy(true); setError(''); setNotice('')
    try {
      const result = await api<{ already_present: boolean }>('/api/datasets/built-in', { method: 'POST' })
      setDatasets(await api<Dataset[]>('/api/datasets'))
      setNotice(result.already_present ? 'Original CC0-1.0 dataset already installed.' : 'Original CC0-1.0 dataset installed.')
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  function selectFile(next: File | null) {
    setFile(next); setPreview(null); setPreviewFile(null); setAcknowledge(false); setError(''); setNotice('')
  }

  function contentType(selected: File) {
    return selected.name.toLowerCase().endsWith('.csv') ? 'text/csv' : 'application/x-ndjson'
  }

  async function previewUpload() {
    if (!file) return
    setBusy(true); setError(''); setPreview(null); setPreviewFile(null); setAcknowledge(false)
    try {
      const result = await api<Preview>('/api/datasets/import/preview', { method: 'POST', headers: { 'Content-Type': contentType(file) }, body: file })
      setPreview(result); setPreviewFile(file)
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!file || !preview || file !== previewFile || (preview.duplicate_content.length > 0 && !acknowledge)) return
    setBusy(true); setError(''); setNotice('')
    const params = new URLSearchParams({ name, version, description, source: source || 'unknown', license: license || 'unknown', acknowledge_duplicates: String(acknowledge) })
    if (datasetId) params.set('dataset_id', datasetId)
    try {
      const imported = await api<{ dataset_id: number; version: string }>(`/api/datasets/import?${params}`, { method: 'POST', headers: { 'Content-Type': contentType(file) }, body: file })
      const rows = await api<Dataset[]>('/api/datasets')
      setDatasets(rows)
      onImported?.(rows, imported.dataset_id, imported.version)
      setNotice('Dataset version saved.'); setPreview(null); setPreviewFile(null); setFile(null); setAcknowledge(false)
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  return <section aria-labelledby="datasets-heading" className="space-y-5">
    <h2 id="datasets-heading" className="text-xl font-semibold">Datasets</h2>
    {!compact && <><p>Install the original CC0-1.0 examples once, or preview a UTF-8 CSV/JSONL file before saving an immutable version.</p><button type="button" onClick={() => void installStarters()} disabled={busy || starterBusy} className="mr-2 rounded bg-slate-900 px-3 py-2 text-white disabled:opacity-50">{starterBusy ? 'Installing…' : 'Install starter sets (5, 10, 20)'}</button><Link to="/experiments" className="underline">Compare datasets</Link><p className="text-sm">Scope: this lab’s local what/where/how interpretation of the Chang survey (<a className="underline" href="https://doi.org/10.1145/3641289" target="_blank" rel="noreferrer">DOI</a>). Checks are deterministic/reference-based by task; summarization overlap is a proxy. These presets overlap, are small convenience samples, and are not an official benchmark or overall-winner measure. Legacy unknown metadata is preserved, not treated as evidence of independence.</p></>}
    <button type="button" onClick={install} disabled={busy} className="rounded bg-slate-900 px-3 py-2 text-white disabled:opacity-50">Install original CC0 dataset</button>
    {loading && <p role="status">Loading datasets…</p>}
    {error && <p role="alert" className="whitespace-pre-wrap text-red-800">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!loading && <div><h3 className="font-semibold">Saved datasets and versions</h3>
      {datasets.length === 0 ? <p>No datasets saved yet.</p> : <ul className="list-inside list-disc">{datasets.map(dataset => <li key={dataset.id}>
        {dataset.name} (dataset ID {dataset.id}; {dataset.origin}; {dataset.license}) — {dataset.description || 'No description'}; source: {dataset.source}. Versions: {dataset.versions.length ? dataset.versions.map(item => `${item.version} (ID ${item.id})`).join(', ') : 'none'}
      </li>)}</ul>}
    </div>}
    {!compact && <details className="rounded border p-3"><summary className="cursor-pointer font-semibold">Existing dataset contents</summary><div className="mt-2 space-y-2"><label className="block">Inspect saved dataset/version <select className="mt-1 block w-full rounded border p-2" value={selectedVersion} onChange={event => setSelectedVersion(event.target.value)}><option value="">Choose dataset version</option>{datasets.flatMap(dataset => dataset.versions.map(item => <option key={item.id} value={`${dataset.id}:${item.version}`}>{dataset.name} / {item.version}</option>))}</select></label>{detailLoading && <p role="status">Loading saved version contents…</p>}{detail && (() => { const dataset = datasets.find(row => String(row.id) === selectedVersion.split(':')[0]); return <div className="space-y-2 rounded border p-3"><p>{dataset?.name} · version {detail.version} · {detail.items.length} items · {dataset?.origin} · {dataset?.license}</p><p>{dataset?.description || 'No dataset description.'} Source: {dataset?.source}. Version source: {String(detail.manifest.source ?? 'unknown')}; license: {String(detail.manifest.license ?? dataset?.license)}; import schema version: {String(detail.manifest.import_schema_version ?? 'not recorded')}.</p><p>Categories: {Object.entries(detail.category_inventory).map(([category, count]) => `${category}: ${count}`).join(', ') || 'none'}</p><p>Content SHA-256: <code className="break-all">{detail.content_sha256}</code></p><details className="text-sm"><summary className="cursor-pointer">Dataset version technical details</summary><pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2 font-mono text-xs">{JSON.stringify(detail.manifest.provenance ?? {}, null, 2)}</pre></details><ol className="list-none space-y-2">{detail.items.map((item, index) => <li key={item.id} className="rounded border p-3"><details><summary className="cursor-pointer"><span className="text-xl font-bold text-slate-900">Question {index + 1} ·</span><span className="ml-2 text-sm font-medium text-slate-700">{item.id} · {item.task_type.replaceAll('_', ' ')}</span><span className="mt-1 block text-sm text-slate-600">Split: {item.split === 'legacy_unknown' ? 'Unknown (not recorded)' : item.split} · Review: {item.review_status === 'legacy_unknown' ? 'Unknown (not recorded)' : item.review_status}</span></summary><div className="ml-4 mt-3 space-y-3"><section><h4 className="font-semibold">Prompt</h4><p className="whitespace-pre-wrap">{item.prompt}</p></section><dl className="space-y-2 text-sm"><div><dt className="font-semibold">Context</dt><dd className="whitespace-pre-wrap">{item.context || 'No context provided.'}</dd></div>{item.choices && <div><dt className="font-semibold">Choices</dt><dd>{item.choices.join(' · ')}</dd></div>}<div><dt className="font-semibold">Reference answers</dt><dd className="mt-1 rounded border border-emerald-200 bg-emerald-50 p-3"><span className="block text-xs font-semibold uppercase tracking-wide text-emerald-900">Reference answers — not a generated response</span><pre className="mt-1 whitespace-pre-wrap break-words font-mono text-sm">{JSON.stringify(item.reference_answers, null, 2)}</pre></dd></div></dl><details className="rounded border p-2 text-sm"><summary className="cursor-pointer font-medium">Technical details</summary><div className="mt-2 space-y-2"><p>Task type: {item.task_type} · Family: {item.family_id ?? 'Not recorded'} · Variant: {item.variant_id ?? 'Not recorded'}</p><p>Split: {item.split} · Review: {item.review_status} · Tags: {item.tags.join(', ') || 'None'} · Source: {item.source} · License: {item.license}</p><div><h5 className="font-medium">Scoring configuration</h5><pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2 font-mono text-xs">{JSON.stringify(item.scoring_config, null, 2)}</pre></div><div><h5 className="font-medium">Item provenance</h5><pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2 font-mono text-xs">{JSON.stringify(item.provenance, null, 2)}</pre></div></div></details></div></details></li>)}</ol></div> })()}</div></details>}
    {!compact && <details className="rounded border p-3"><summary className="cursor-pointer font-semibold">Upload schema and validation</summary><div className="mt-2 space-y-2 text-sm"><p>Upload UTF-8 CSV or JSONL (JSON Lines), up to 5 MiB and 5,000 nonblank rows. CSV headers must be unique and supported; JSONL has one JSON object per nonblank line. At least one row is required.</p><p><strong>Required per item:</strong> <code>id</code>, <code>task_type</code>, <code>prompt</code>, <code>reference_answers</code>, and <code>scoring_config</code>. IDs must be unique. Accepted <code>task_type</code> values are <code>multiple_choice</code>, <code>short_factual</code>, <code>extractive_qa</code>, <code>arithmetic</code>, <code>classification</code>, <code>structured_extraction</code>, <code>summarization</code>, and <code>instruction_following</code>.</p><p><strong>Optional:</strong> <code>context</code>, <code>choices</code> (required for multiple choice), <code>tags</code>, <code>source</code>, <code>license</code>, <code>split</code>, <code>family_id</code>, <code>variant_id</code>, <code>provenance</code>, and <code>review_status</code>. Accepted split values: <code>dev</code>, <code>calibration</code>, <code>test</code>, <code>legacy_unknown</code>. Accepted review status values: <code>draft</code>, <code>pending</code>, <code>reviewed</code>, <code>legacy_unknown</code>. Defaults include empty context/tags, unknown source/license, <code>legacy_unknown</code> split, and draft review status (legacy_unknown for that split).</p><p>Known splits require a globally namespaced <code>family_id</code>; a family cannot appear in more than one split. CSV encodes <code>reference_answers</code>, <code>choices</code>, <code>scoring_config</code>, <code>tags</code>, and <code>provenance</code> as JSON text cells. Task-specific scorer configs and reference shapes are validated; use current dataset item details as examples for other task types.</p><p>Minimal valid JSONL (<code>short_factual</code>):</p><pre className="overflow-x-auto rounded bg-slate-50 p-2 text-xs"><code>{'{"id":"example-1","task_type":"short_factual","prompt":"What is 2 + 2?","reference_answers":["4"],"scoring_config":{"metric":"normalized_exact_match","normalization":"unicode_nfc_casefold_trim_collapse_whitespace"}}'}</code></pre><p>Field lengths, references, choices, tags, provenance, duplicates, and scorer declarations are validated by the server; preview does not bypass save-time validation.</p></div></details>}
    <form onSubmit={save} className="space-y-3 border-t pt-4">
      <h3 className="font-semibold">Import a version</h3>
      <label className="block">CSV or JSONL file (.csv or .jsonl, up to 5 MiB)
        <input className="block" type="file" accept=".csv,.jsonl,.ndjson,text/csv,application/x-ndjson" required onChange={event => selectFile(event.target.files?.[0] ?? null)} />
      </label>
      <button type="button" disabled={!file || busy} onClick={previewUpload} className="rounded border px-3 py-2 disabled:opacity-50">{busy ? 'Working…' : 'Preview file'}</button>
      {preview && <div role="status" className="space-y-1 rounded border p-3">
        <p>{preview.row_count} rows · SHA-256: <code className="break-all">{preview.content_sha256}</code></p>
        <p>Categories: {Object.entries(preview.category_inventory).map(([category, count]) => `${category}: ${count}`).join(', ')}</p>
        {preview.duplicate_content.length > 0 && <div><p className="font-semibold text-amber-900">Duplicate normalized content detected:</p>
          <ul className="list-inside list-disc">{preview.duplicate_content.map((entry, index) => <li key={index}>Row {entry.row}, ID {entry.id}, matches row {entry.matches_row}</li>)}</ul>
          <label className="block"><input type="checkbox" checked={acknowledge} onChange={event => setAcknowledge(event.target.checked)} /> I acknowledge these duplicate-content warnings</label>
        </div>}
      </div>}
      <label className="block">Dataset name <input className="block w-full rounded border p-2" value={name} onChange={event => setName(event.target.value)} maxLength={255} required /></label>
      <label className="block">Version <input className="block w-full rounded border p-2" value={version} onChange={event => setVersion(event.target.value)} maxLength={80} required /></label>
      <label className="block">Add to existing dataset (optional) <select className="block w-full rounded border p-2" value={datasetId} onChange={event => { setDatasetId(event.target.value); const selected = datasets.find(row => String(row.id) === event.target.value); if (selected) setName(selected.name) }}><option value="">Create new dataset</option>{datasets.map(row => <option key={row.id} value={row.id}>{row.name} (ID {row.id})</option>)}</select></label>
      <label className="block">Description (optional) <input className="block w-full rounded border p-2" value={description} onChange={event => setDescription(event.target.value)} maxLength={10000} /></label>
      <label className="block">Source (unknown if blank) <input className="block w-full rounded border p-2" value={source} onChange={event => setSource(event.target.value)} maxLength={512} /></label>
      <label className="block">License (unknown if blank) <input className="block w-full rounded border p-2" value={license} onChange={event => setLicense(event.target.value)} maxLength={100} /></label>
      <button type="submit" disabled={busy || !preview || file !== previewFile || (preview.duplicate_content.length > 0 && !acknowledge)} className="rounded bg-slate-900 px-3 py-2 text-white disabled:opacity-50">Save dataset version</button>
    </form>
  </section>
}
