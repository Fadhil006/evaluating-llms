import { useEffect, useState, type FormEvent } from 'react'

export type Dataset = { id: number; name: string; description: string; origin: string; source: string; license: string; versions: { id: number; version: string }[] }
type Duplicate = { row: number; id: string; matches_row: number }
type Preview = { row_count: number; content_sha256: string; category_inventory: Record<string, number>; duplicate_content: Duplicate[] }

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

export default function Datasets() {
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

  useEffect(() => {
    let active = true
    api<Dataset[]>('/api/datasets').then(rows => { if (active) setDatasets(rows) })
      .catch((cause: Error) => { if (active) setError(cause.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

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
      await api(`/api/datasets/import?${params}`, { method: 'POST', headers: { 'Content-Type': contentType(file) }, body: file })
      setDatasets(await api<Dataset[]>('/api/datasets'))
      setNotice('Dataset version saved.'); setPreview(null); setPreviewFile(null); setFile(null); setAcknowledge(false)
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  return <section aria-labelledby="datasets-heading" className="space-y-5">
    <h2 id="datasets-heading" className="text-xl font-semibold">Datasets</h2>
    <p>Install the original CC0-1.0 examples once, or preview a UTF-8 CSV/JSONL file before saving an immutable version.</p>
    <button type="button" onClick={install} disabled={busy} className="rounded bg-slate-900 px-3 py-2 text-white disabled:opacity-50">Install original CC0 dataset</button>
    {loading && <p role="status">Loading datasets…</p>}
    {error && <p role="alert" className="whitespace-pre-wrap text-red-800">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!loading && <div><h3 className="font-semibold">Saved datasets and versions</h3>
      {datasets.length === 0 ? <p>No datasets saved yet.</p> : <ul className="list-inside list-disc">{datasets.map(dataset => <li key={dataset.id}>
        {dataset.name} (dataset ID {dataset.id}; {dataset.origin}; {dataset.license}) — {dataset.description || 'No description'}; source: {dataset.source}. Versions: {dataset.versions.length ? dataset.versions.map(item => `${item.version} (ID ${item.id})`).join(', ') : 'none'}
      </li>)}</ul>}
    </div>}
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
