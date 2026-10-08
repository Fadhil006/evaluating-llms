import { useEffect, useState } from 'react'

type Provider = {
  slug: string
  credential_configured: boolean
  connection_status: string
  checked_at: string | null
  policy_links: Record<string, string>
}
type Model = {
  id: number
  provider: string
  model_id: string
  name: string
  endpoint: string
  context_length: number | null
  supported_parameters: string[]
  availability: string
  credential_configured: boolean
  pricing_source: string | null
  pricing_evidence: Record<string, unknown>
  checked_at: string | null
  eligibility: { allowed: boolean; reason: string; checked_at: string | null; model_id: string }
}
type Refresh = Record<string, { status: string; reason?: string; models?: number }>
type Quota = { status: string; reason?: string; quota: { free_limit: number | null; free_used: number | null; observed_at: string } | null }

const reasons: Record<string, string> = {
  verified_zero: 'Verified zero-price catalog evidence (backend decision)',
  stale_pricing: 'Stale or expired pricing evidence — refresh required',
  unknown_pricing: 'Unknown or incomplete pricing evidence',
  nonzero_or_invalid_pricing: 'Nonzero or invalid pricing — blocked',
  conditional_pricing: 'Conditional pricing cannot be verified zero',
  official_price_evidence_required: 'Dated official price evidence required',
  unavailable: 'Temporarily unavailable at last observation',
  unsupported_endpoint: 'Unsupported endpoint for chat generation',
  unstable_identity: 'No stable exact model identity',
  unknown_provider: 'Unknown provider',
  unsupported_parameter: 'Unsupported request parameter',
  invalid_request: 'Invalid request',
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) throw new Error('Request failed')
  return response.json() as Promise<T>
}

export default function Models({ mode }: { mode?: 'live' | 'demo' }) {
  const [models, setModels] = useState<Model[]>([])
  const [providers, setProviders] = useState<Provider[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [refreshResult, setRefreshResult] = useState<Refresh | null>(null)
  const [quota, setQuota] = useState<Record<string, Quota>>({})
  const [checking, setChecking] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    Promise.all([json<Model[]>('/api/models'), json<Provider[]>('/api/providers')])
      .then(([catalog, connections]) => {
        if (active) { setModels(catalog); setProviders(connections); setError(''); setLoading(false) }
      })
      .catch(() => { if (active) { setError('Could not load catalog or provider status. Try reloading the page.'); setLoading(false) } })
    return () => { active = false }
  }, [])

  async function refresh() {
    setRefreshing(true)
    setError('')
    setRefreshResult(null)
    try {
      const result = await json<Refresh>('/api/models/refresh', { method: 'POST' })
      setRefreshResult(result)
      const [catalog, connections] = await Promise.all([json<Model[]>('/api/models'), json<Provider[]>('/api/providers')])
      setModels(catalog)
      setProviders(connections)
    } catch {
      setError('Refresh or catalog reload failed. Displayed observations may be old; reload the page to retry.')
    } finally {
      setRefreshing(false)
    }
  }

  async function checkQuota(slug: string) {
    setChecking(slug); setError('')
    try {
      const result = await json<Quota>(`/api/providers/${slug}/check`, { method: 'POST' })
      setQuota(rows => ({ ...rows, [slug]: result }))
    } catch {
      setError(`Could not check ${slug} account limits. Existing observations are unchanged.`)
    } finally { setChecking(null) }
  }

  const listedModels = models.filter(model => mode === 'demo'
    ? model.provider === 'fixture'
    : model.eligibility?.allowed === true && model.eligibility.checked_at != null &&
      model.eligibility.model_id === model.model_id && !!model.pricing_source)

  return <section aria-labelledby="models-heading">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="models-heading" className="text-xl font-semibold">Models</h2>
      <button type="button" onClick={refresh} disabled={loading || refreshing} className="rounded bg-slate-900 px-4 py-2 text-white hover:bg-slate-700 focus-visible:outline-2 disabled:cursor-not-allowed disabled:opacity-50">{refreshing ? 'Refreshing…' : 'Refresh catalog'}</button>
    </div>
    <p className="mt-3 text-sm text-slate-600">{mode === 'live' ? 'Live mode · saved provider catalog observations; timestamps show when evidence was checked, not current availability.' : mode === 'demo' ? 'DEMONSTRATION MODE · refresh creates two synthetic fixture routes locally; it makes no network calls and does not report live model availability.' : 'Checking execution mode · catalog provenance not yet confirmed.'}</p>
    <p className="mt-2 text-sm text-slate-600">Only routes with fresh backend-verified zero-cost evidence are listed in live mode. Execution still rechecks current evidence before every run and request.</p>
    {loading && <p role="status" className="mt-5">Loading models and providers…</p>}
    {error && <p role="alert" className="mt-5 rounded bg-red-50 p-3 text-red-900">{error}</p>}
    {refreshResult && <div role="status" className="mt-4 rounded bg-slate-50 p-3 text-sm"><p className="font-medium">Refresh results</p><ul className="mt-1 list-inside list-disc">{Object.entries(refreshResult).map(([slug, result]) => <li key={slug}>{slug}: {result.status}{result.models != null ? ` (${result.models} models)` : ''}{result.reason ? ` — ${result.reason}` : ''}{result.status !== 'reachable' ? ' — existing snapshots were not revalidated' : ''}</li>)}</ul></div>}
    {!loading && <>
      <h3 className="mt-6 text-lg font-semibold">Providers</h3>
      {!error && providers.length === 0 ? <p className="mt-2 text-slate-600">No provider status available.</p> : <ul className="mt-2 grid gap-3 sm:grid-cols-2">{providers.map(provider => <li key={provider.slug} className="rounded border border-slate-200 p-4">
        <h4 className="font-semibold">{provider.slug}</h4>
         <p className="text-sm">Credential: {provider.credential_configured ? 'Configured' : provider.slug === 'opencode_zen' ? 'Not configured · listed allowlisted free models may support anonymous requests' : 'Not configured'}</p>
         <p className="text-sm">Catalog connection: {provider.connection_status} · checked: {provider.checked_at ?? 'Never'}</p>
         {provider.slug !== 'fixture' && <button type="button" onClick={() => void checkQuota(provider.slug)} disabled={mode === 'demo' || !provider.credential_configured || checking !== null} className="mt-2 rounded border px-3 py-1 disabled:opacity-50">{mode === 'demo' ? 'Live checks disabled in demo mode' : checking === provider.slug ? 'Checking account limits…' : 'Check account limits'}</button>}
         {quota[provider.slug] && <p className="mt-2 text-sm">Account limits: {quota[provider.slug].status}{quota[provider.slug].reason ? ` — ${quota[provider.slug].reason}` : ''}{quota[provider.slug].quota ? ` · free requests ${quota[provider.slug].quota?.free_used ?? 'unknown'} used / ${quota[provider.slug].quota?.free_limit ?? 'unknown'} limit at ${quota[provider.slug].quota?.observed_at}` : ' · request quota unknown'}</p>}
        <p className="text-sm">Policy: {Object.entries(provider.policy_links).map(([name, href]) => <span key={name} className="mr-3"><a className="underline" href={href} target="_blank" rel="noopener noreferrer">{name} ↗</a></span>)}</p>
      </li>)}</ul>}
       <h3 className="mt-6 text-lg font-semibold">{mode === 'demo' ? 'Synthetic demonstration models' : 'Verified-free models'}</h3>
       {!error && models.length === 0 ? <p className="mt-2 text-slate-600">No models discovered yet. Refresh the catalog to check configured providers.</p>
         : !error && listedModels.length === 0 ? <p role="status" className="mt-2 text-slate-700">No models currently pass the backend’s fresh, verified-zero pricing checks ({models.length} catalog entries checked). Paid, unknown-price, unsupported and unavailable models are hidden. A `:free` model ID alone is not evidence; refresh after provider pricing changes.</p>
         : <><p className="mt-2 text-sm text-slate-600">{mode === 'demo' ? `${listedModels.length} synthetic fixture route(s); not live models or free-model claims.` : `Showing ${listedModels.length} route(s) with fresh backend-verified zero-cost evidence; other catalog entries are hidden.`}</p><ul className="mt-2 space-y-4">{listedModels.map(model => {
        const eligible = model.eligibility?.allowed === true && model.eligibility.checked_at != null && model.eligibility.model_id === model.model_id && !!model.pricing_source
        return <li key={model.id}><article className="rounded border border-slate-200 p-4">
          <h4 className="font-semibold">{model.name}</h4>
          <p className="mt-1 break-all text-sm">Exact route: <code>{model.provider} / {model.model_id}</code></p>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
           <div><dt className="font-medium">Availability</dt><dd>{mode === 'demo' && model.provider === 'fixture' ? 'DEMONSTRATION synthetic route' : model.availability}</dd></div>
            <div><dt className="font-medium">Endpoint</dt><dd>{model.endpoint}</dd></div>
            <div><dt className="font-medium">Context window</dt><dd>{model.context_length == null ? 'Unknown' : `${model.context_length.toLocaleString()} tokens`}</dd></div>
            <div><dt className="font-medium">Supported parameters</dt><dd>{model.supported_parameters.length ? model.supported_parameters.join(', ') : 'Unknown / none reported'}</dd></div>
             <div className="sm:col-span-2"><dt className="font-medium">Pricing evidence source</dt><dd className="break-all">{model.pricing_source ?? 'Unknown'}</dd></div>
             <div className="sm:col-span-2"><dt className="font-medium">Recorded prices</dt><dd>{model.pricing_evidence?.official_pricing ? Object.entries(model.pricing_evidence.official_pricing as Record<string, string>).map(([name, price]) => `${name}: ${price}`).join(' · ') : Object.entries(model.pricing_evidence ?? {}).filter(([name, value]) => typeof value === 'string' && (['prompt', 'completion', 'request', 'input_cache_read', 'input_cache_write', 'internal_reasoning'].includes(name))).map(([name, value]) => `${name}: ${String(value)}`).join(' · ') || 'No usable machine-readable price evidence'}</dd></div>
            <div><dt className="font-medium">Pricing checked at</dt><dd>{model.checked_at ?? 'Never'}</dd></div>
             <div><dt className="font-medium">Free-only catalog decision</dt><dd className={eligible && model.credential_configured ? 'font-semibold text-emerald-800' : 'font-semibold text-amber-900'}>{mode === 'demo' && model.provider === 'fixture' ? 'Not a live model; synthetic demonstration only' : eligible && !model.credential_configured ? 'Zero-price evidence verified; provider key not configured, so execution is unavailable' : eligible ? 'Eligible at last check' : 'Blocked'}{!(mode === 'demo' && model.provider === 'fixture') && !eligible && <> — {model.eligibility?.allowed ? 'Missing matching dated backend evidence' : reasons[model.eligibility?.reason] ?? model.eligibility?.reason ?? 'No backend eligibility evidence'}</>}</dd></div>
          </dl>
        </article></li>
       })}</ul></>}
    </>}
  </section>
}
