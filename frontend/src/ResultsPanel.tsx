import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from './Datasets'

type Metric = { metric: string; scorer_version: string; value: number | null; normalized_answer: string | null; parse_status: string; explanation: string; quality_denominator: number | null; scheduled_denominator: number | null }
type Answer = { id: number; raw_text: string; reference_answers: string[]; identity_mismatch: boolean; truncated: boolean; finish_reason: string | null; metrics: Metric[] }
type Row = { job_id: number; model_slot: number; provider: string; model_id: string; item_id: string; task_type: string; prompt: string; context: string | null; choices: unknown; reference_answers: string[]; repetition: number; variant: string; job_status: string; status: string; attempt_error: string | null; duration_ms: number | null; usage: { prompt_tokens?: number; completion_tokens?: number } | null; response: Answer | null }
type Page = { total: number; offset: number; limit: number; items: Row[] }
type Summary = { model_slot: number; provider: string; model_id: string; task_type: string; metric: string; scheduled_jobs: number; responses: number; complete: number; truncated: number; parseable: number; metric_eligible: number; missing_reference: number; failures: number; pending: number; cancelled: number; identity_mismatch: number; format_failures: number; quality: number | null; quality_denominator: number; overall_success: number | null; overall_success_denominator: number | null; macro_f1: number | null; latency_sample_count: number; median_request_latency_ms: number | null; p95_request_latency_ms: number | null; usage_sample_count: number; prompt_tokens_total: number | null; completion_tokens_total: number | null }
export type DashboardReport = { summaries: Summary[]; common_completed: { task_type: string; metric: string; count: number; keys: { item_id: string; repetition: number; variant: string }[]; models: { model_slot: number; quality: number | null; omitted_count: number }[] }[] }

const show = (value: unknown) => value == null ? 'Not reported' : String(value)

export default function ResultsPanel({ experimentId, report }: { experimentId: number; report: DashboardReport }) {
  const [metric, setMetric] = useState('all'), [model, setModel] = useState('all'), [task, setTask] = useState('all'), [status, setStatus] = useState('all')
  const [offset, setOffset] = useState(0), [page, setPage] = useState<Page | null>(null), [loading, setLoading] = useState(false), [error, setError] = useState('')
  const [expandedJobId, setExpandedJobId] = useState<number | null>(null)
  const rows = useMemo(() => report.summaries.filter(row => (metric === 'all' || row.metric === metric) && (model === 'all' || String(row.model_slot) === model) && (task === 'all' || row.task_type === task)), [report, metric, model, task])
  const tasks = [...new Set(report.summaries.map(row => row.task_type))], metrics = [...new Set(report.summaries.map(row => row.metric))]
  useEffect(() => { setOffset(0); setExpandedJobId(null) }, [experimentId, metric, model, task, status])
  useEffect(() => { setExpandedJobId(null) }, [offset])
  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    const params = new URLSearchParams({ offset: String(offset), limit: '50', status })
    if (model !== 'all') params.set('model_slot', model)
    if (task !== 'all') params.set('task_type', task)
    api<Page>(`/api/experiments/${experimentId}/responses?${params}`).then(data => { if (active) setPage(data) }).catch((cause: Error) => { if (active) setError(cause.message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [experimentId, offset, model, task, status])
  const grouped = new Map<string, Row[]>()
  for (const row of page?.items ?? []) { const key = `${row.item_id}\u0000${row.repetition}\u0000${row.variant}`; grouped.set(key, [...(grouped.get(key) ?? []), row]) }
  const chart = rows.filter(row => row.quality !== null).map(row => ({ label: `${row.provider}/${row.model_id} · ${row.task_type} · ${row.metric}`, quality: row.quality! * 100 }))
  return <section className="mt-4 space-y-4 border-t pt-4" aria-labelledby={`results-${experimentId}`}>
    <h4 id={`results-${experimentId}`} className="font-semibold">Results dashboard</h4>
    <p>Route measurements reflect this provider/model route under the recorded run conditions; they do not measure intrinsic model speed.</p>
    <nav aria-label={`Export experiment ${experimentId}`} className="flex flex-wrap gap-3">{(['csv', 'json', 'html', 'markdown'] as const).map(format => <a key={format} className="rounded border px-3 py-2 underline" href={`/api/experiments/${experimentId}/export?format=${format}`} download={`experiment-${experimentId}.${format}`}>Download {format === 'json' ? 'JSON manifest' : format.toUpperCase()}</a>)}</nav>
    <div className="flex flex-wrap gap-3">
      <label>Metric <select className="rounded border p-2" value={metric} onChange={e => setMetric(e.target.value)}><option value="all">All metrics</option>{metrics.map(v => <option key={v}>{v}</option>)}</select></label>
      <label>Model <select className="rounded border p-2" value={model} onChange={e => setModel(e.target.value)}><option value="all">All models</option>{[...new Set(report.summaries.map(row => row.model_slot))].map(slot => <option key={slot} value={slot}>{report.summaries.find(row => row.model_slot === slot)?.provider} / {report.summaries.find(row => row.model_slot === slot)?.model_id}</option>)}</select></label>
      <label>Task <select className="rounded border p-2" value={task} onChange={e => setTask(e.target.value)}><option value="all">All tasks</option>{tasks.map(v => <option key={v}>{v}</option>)}</select></label>
      <label>Response status <select className="rounded border p-2" value={status} onChange={e => setStatus(e.target.value)}>{['all','answered','malformed','truncated','failed','pending','cancelled'].map(v => <option key={v}>{v}</option>)}</select></label>
    </div>
    {!rows.length ? <p>No aggregate results match these filters.</p> : <>
      <h5 className="font-medium">Task metric quality (percent; denominator = metric-eligible responses)</h5>
      <div role="img" aria-label="Bar chart of task metric quality percentages by model route" className="h-80 w-full"><ResponsiveContainer width="100%" height="100%"><BarChart data={chart} accessibilityLayer margin={{ bottom: 65, left: 10, right: 15 }}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="label" angle={-35} textAnchor="end" interval={0} height={90}/><YAxis domain={[0,100]} label={{ value: 'Quality (%)', angle: -90, position: 'insideLeft' }}/><Tooltip/><Bar dataKey="quality" name="Quality (%)" fill="#334155"/></BarChart></ResponsiveContainer></div>
      <div className="overflow-x-auto"><table className="w-full border-collapse text-left text-sm"><caption className="sr-only">Filtered task metrics and explicit denominators</caption><thead><tr>{['Route','Task / metric','Quality (eligible responses)','Complete / scheduled','Failure / pending / cancelled','Truncated / malformed / mismatch','Median / p95 route latency (ms; n)','Usage samples','Prompt / completion tokens','Overall success (scheduled denominator)'].map(x=><th className="border p-2" key={x}>{x}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={`${r.model_slot}-${r.task_type}-${r.metric}-${i}`}><td className="border p-2">{r.provider} / {r.model_id}</td><td className="border p-2">{r.task_type} / {r.metric}{r.macro_f1 !== null ? `; macro F1 ${r.macro_f1.toFixed(3)}` : ''}</td><td className="border p-2">{r.quality === null ? '—' : `${(r.quality*100).toFixed(1)}% (${r.quality_denominator} eligible)`}</td><td className="border p-2">{r.complete} / {r.scheduled_jobs}</td><td className="border p-2">{r.failures} / {r.pending} / {r.cancelled}</td><td className="border p-2">{r.truncated} / {r.format_failures} / {r.identity_mismatch}</td><td className="border p-2">{show(r.median_request_latency_ms)} / {show(r.p95_request_latency_ms)} (n={r.latency_sample_count})</td><td className="border p-2">{r.usage_sample_count}</td><td className="border p-2">{show(r.prompt_tokens_total)} / {show(r.completion_tokens_total)}</td><td className="border p-2">{r.overall_success === null ? '—' : `${(r.overall_success*100).toFixed(1)}% (${r.overall_success_denominator} scheduled)`}</td></tr>)}</tbody></table></div>
      <h5 className="font-medium">Common-completed coverage (same item, repetition and variant)</h5>
      <ul>{report.common_completed.filter(r => (task === 'all' || r.task_type === task) && (metric === 'all' || r.metric === metric)).map((r,i)=><li key={`${r.task_type}-${r.metric}-${i}`}>{r.task_type} / {r.metric}: {r.count} shared keys{r.models.map(m=>` · slot ${m.model_slot}: ${m.quality === null ? '—' : `${(m.quality*100).toFixed(1)}%`} (${m.omitted_count} omitted)`)}</li>)}</ul>
    </>}
    <h5 className="font-medium">Answer inspection — non-blinded route identities</h5>
    <p>Each row compares selected routes only when item, repetition and variant match. Page through all matching scheduled jobs to inspect missing responses too.</p>
    {loading && <p role="status">Loading response page…</p>}{error && <p role="alert">Could not load responses: {error}</p>}
    {!loading && !error && page?.total === 0 && <p>No responses or scheduled jobs match these filters.</p>}
    {[...grouped.values()].map(group => <article key={`${group[0].item_id}-${group[0].repetition}-${group[0].variant}`} className="space-y-2 rounded border p-3">
      <h6 className="font-medium">{group[0].task_type} · item {group[0].item_id} · repetition {group[0].repetition} · variant {group[0].variant}</h6>
      <p><strong>Prompt:</strong> {group[0].prompt}</p>{group[0].context && <p><strong>Context:</strong> {group[0].context}</p>}
      {group[0].choices != null && <><strong>Choices:</strong><pre className="whitespace-pre-wrap">{JSON.stringify(group[0].choices,null,2)}</pre></>}
      <p><strong>Reference answers:</strong> {group[0].reference_answers.join(' | ') || 'Missing reference answers'}</p>
      <div className="grid gap-3 md:grid-cols-2">{group.map(row => <section key={row.job_id} className="min-w-0 rounded border p-3">
        <h6 className="font-semibold">{row.provider} / {row.model_id}</h6>
        <p>Status: {row.status} (job {row.job_status}){row.attempt_error ? ` · error: ${row.attempt_error}` : ''}</p>
        {row.response ? <>
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words">{row.response.raw_text}</pre>
          {row.response.truncated && <p role="status">Truncated response (finish reason: {show(row.response.finish_reason)}).</p>}
          {row.response.identity_mismatch && <p>Returned route identity mismatch (returned identity is preserved in result detail).</p>}
          {(() => {
            const responseMetrics = row.response!.metrics.filter(m => metric === 'all' || m.metric === metric)
            const detailId = `score-detail-${experimentId}-${row.job_id}`
            const expanded = expandedJobId === row.job_id
            return responseMetrics.length > 0 ? <>
              <ul aria-label="Compact score summary">{responseMetrics.map((m,i) => <li key={`${m.metric}-${m.scorer_version}-${i}`}><strong>{m.metric}</strong>: {show(m.value)} · {m.parse_status}</li>)}</ul>
              <button type="button" className="underline" aria-expanded={expanded} aria-controls={detailId} onClick={() => setExpandedJobId(expanded ? null : row.job_id)}>{expanded ? 'Hide score details' : 'Show score details'}</button>
              <div id={detailId} hidden={!expanded}>{responseMetrics.map((m,i) => <div key={`${m.metric}-${m.scorer_version}-${i}`}><p><strong>{m.metric}</strong> normalized answer: {show(m.normalized_answer)}</p><p>Metric denominator: {show(m.quality_denominator)} eligible responses; scheduled denominator: {show(m.scheduled_denominator)} jobs.</p><p>Scorer explanation: {m.explanation}</p></div>)}</div>
            </> : <p>No scoring details for this metric filter.</p>
          })()}
        </> : <p>No response recorded; this is distinct from an incorrect answer.</p>}
        <p>Route latency: {show(row.duration_ms)} ms · token usage: {row.usage ? `prompt ${show(row.usage.prompt_tokens)}, completion ${show(row.usage.completion_tokens)}` : 'not reported'}</p>
      </section>)}</div>
      {group.length < 2 && <p>Only one selected-model row for this key is present on this page.</p>}
    </article>)}
    {page && page.total > 0 && <nav aria-label="Response results pages" className="flex items-center gap-3"><button className="rounded border px-3 py-2" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0,offset-50))}>Previous page</button><span>Showing {offset+1}–{Math.min(offset+page.items.length,page.total)} of {page.total} scheduled jobs</span><button className="rounded border px-3 py-2" disabled={offset+page.limit >= page.total || loading} onClick={() => setOffset(offset+page.limit)}>Next page</button></nav>}
  </section>
}
