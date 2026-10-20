import { useEffect, useMemo, useState } from 'react'
import { api } from './Datasets'

type Metric = { metric: string; scorer_version: string; value: number | null; normalized_answer: string | null; parse_status: string; explanation: string; quality_denominator: number | null; scheduled_denominator: number | null }
type Answer = { id: number; raw_text: string; reference_answers: string[]; identity_mismatch: boolean; truncated: boolean; finish_reason: string | null; metrics: Metric[] }
type Row = { job_id: number; model_slot: number; provider: string; model_id: string; item_id: string; task_type: string; prompt: string; context: string | null; choices: unknown; reference_answers: string[]; repetition: number; variant: string; job_status: string; status: string; attempt_error: string | null; duration_ms: number | null; usage: { prompt_tokens?: number; completion_tokens?: number } | null; response: Answer | null }
type Page = { total: number; offset: number; limit: number; items: Row[] }
type Summary = { model_slot: number; provider: string; model_id: string; task_type: string; metric: string; scheduled_jobs: number; responses: number; complete: number; truncated: number; parseable: number; metric_eligible: number; missing_reference: number; failures: number; pending: number; cancelled: number; identity_mismatch: number; format_failures: number; quality: number | null; quality_denominator: number; overall_success: number | null; overall_success_denominator: number | null; macro_f1: number | null; latency_sample_count: number; median_request_latency_ms: number | null; p95_request_latency_ms: number | null; usage_sample_count: number; prompt_tokens_total: number | null; completion_tokens_total: number | null }
export type DashboardReport = { summaries: Summary[]; common_completed: { task_type: string; metric: string; count: number; keys: { item_id: string; repetition: number; variant: string }[]; models: { model_slot: number; quality: number | null; omitted_count: number }[] }[] }
type AnalysisResult = { task_type: string; metric: string; family_n: number | null; model_means: Record<string, number | null>; paired_delta: number | null; interval_95: { low: number; high: number; degenerate?: boolean } | null; missing_family_metadata: boolean; omitted_families: (string | number)[][] }
type Analysis = { id: number | string; sha256: string; manifest: Record<string, unknown>; results: AnalysisResult[] }

const show = (value: unknown) => value == null ? 'Not reported' : String(value)
const metricName = (metric: string) => metric.replaceAll('_', ' ')
const metricKind = (metric: string) => ['token_f1', 'rouge_l_f1'].includes(metric) ? 'Proxy measure' : 'Deterministic check'
const metricGuide: Record<string, string> = {
  label_accuracy: 'One if the single declared class/choice label matches an accepted reference; otherwise zero.',
  raw_exact_match: 'One if the original answer exactly matches a reference, including case and whitespace.',
  normalized_exact_match: 'One if NFC-normalized, case-folded, whitespace-collapsed text matches a reference; punctuation is retained.',
  token_f1: 'Word-token overlap F1 against the best reference (multiset token counts); a partial-overlap proxy, not factuality.',
  numeric_exact: 'One if the parsed finite number is within the declared absolute/relative tolerance; units are not accepted.',
  json_valid: 'One if the response is valid JSON with no duplicate keys or non-finite numbers.',
  schema_valid: 'One if JSON has exactly the declared fields and primitive types.',
  field_exact: 'One if schema-valid JSON exactly matches an accepted reference object.',
  json_exact_fields: 'Task grouping label for JSON checks; inspect json_valid, schema_valid, and field_exact individually.',
  rouge_l_f1: 'Word-sequence longest-common-subsequence F1 against the best reference; overlap proxy, not factuality.',
  instruction_all_checks: 'One only when every declared exact-text, exact-JSON, substring, or word-count check passes.',
  instruction_pooled_passed: 'Passed declared checks divided by all declared checks; prompts with more checks contribute more.',
  instruction_pooled_total: 'Count of declared checks; this is a denominator, not a quality score.',
}

export default function ResultsPanel({ experimentId, report }: { experimentId: number; report: DashboardReport }) {
  const [metric, setMetric] = useState('all'), [model, setModel] = useState('all'), [task, setTask] = useState('all'), [status, setStatus] = useState('all')
  const [page, setPage] = useState<Page | null>(null), [loading, setLoading] = useState(false), [error, setError] = useState('')
  const [questionIndex, setQuestionIndex] = useState(0), [hideNames, setHideNames] = useState(false)
  const [analyses, setAnalyses] = useState<Analysis[]>([]), [analysisId, setAnalysisId] = useState(''), [analysisBusy, setAnalysisBusy] = useState(false), [analysisError, setAnalysisError] = useState('')
  const summaries = report.summaries
  const rows = useMemo(() => summaries.filter(row => (metric === 'all' || row.metric === metric) && (model === 'all' || String(row.model_slot) === model) && (task === 'all' || row.task_type === task)), [summaries, metric, model, task])
  const tasks = [...new Set(summaries.map(row => row.task_type))], metrics = [...new Set(summaries.map(row => row.metric))]
  const routeSlots = [...new Set(summaries.map(row => row.model_slot))].sort((a,b)=>a-b)
  const routeLabel = (slot: number) => {
    const row = summaries.find(item=>item.model_slot===slot)
    const label = `Model ${String.fromCharCode(65 + Math.max(0,routeSlots.indexOf(slot)))}`
    return hideNames ? label : `${label} (${row?.provider === 'openrouter' ? 'OpenRouter' : row?.provider === 'opencode_zen' ? 'OpenCode Zen' : row?.provider === 'fixture' ? 'Demonstration fixtures' : row?.provider ?? 'provider'})`
  }
  // Counts are identical across a task's metric rows; select one row per model/task to avoid double counting.
  const taskRows = useMemo(() => [...new Map(summaries.map(row => [`${row.model_slot}\0${row.task_type}`, row])).values()], [summaries])
  const summaryCards = routeSlots.filter(slot => model === 'all' || String(slot) === model).flatMap(slot => {
    const items = taskRows.filter(row => row.model_slot === slot && (task === 'all' || row.task_type === task))
    if (!items.length) return []
    const card = { ...items[0] }
    for (const field of ['scheduled_jobs', 'responses', 'failures', 'pending', 'cancelled', 'truncated', 'format_failures', 'identity_mismatch'] as const) card[field] = items.reduce((sum, row) => sum + row[field], 0)
    return [card]
  })
  useEffect(() => { setQuestionIndex(0) }, [experimentId, metric, model, task, status])
  useEffect(() => {
    let active = true
    setAnalysisError(''); setAnalysisId('')
    api<Analysis[] | { items: Analysis[] }>(`/api/experiments/${experimentId}/analyses`).then(data => {
      if (!active) return
      const snapshots = Array.isArray(data) ? data : data.items
      setAnalyses(snapshots); if (snapshots[0]) setAnalysisId(String(snapshots[0].id))
    }).catch((cause: Error) => { if (active) { setAnalyses([]); setAnalysisError(cause.message) } })
    return () => { active = false }
  }, [experimentId])
  const selectedAnalysis = analyses.find(snapshot => String(snapshot.id) === analysisId)
  async function createAnalysis() {
    setAnalysisBusy(true); setAnalysisError('')
    try {
      const created = await api<Analysis>(`/api/experiments/${experimentId}/analyses`, { method: 'POST' })
      const snapshot = created.results ? created : await api<Analysis>(`/api/experiments/${experimentId}/analyses/${created.id}`)
      setAnalyses(current => [snapshot, ...current.filter(row => String(row.id) !== String(snapshot.id))]); setAnalysisId(String(snapshot.id))
    } catch (cause) { setAnalysisError((cause as Error).message) } finally { setAnalysisBusy(false) }
  }
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    async function load() {
      const collected: Row[] = []
      let offset = 0, total = 0
      do {
        const params = new URLSearchParams({ offset: String(offset), limit: '100', status: 'all' })
        if (task !== 'all') params.set('task_type', task)
        const result = await api<Page>(`/api/experiments/${experimentId}/responses?${params}`, { signal: controller.signal })
        collected.push(...result.items); total = result.total; offset += result.limit
      // ponytail: fetch-all grouping trades memory/load time for never splitting paired rows; add cursor grouping if experiment sizes grow.
      } while (offset < total && !controller.signal.aborted)
      if (!controller.signal.aborted) setPage({ total, offset: 0, limit: total, items: collected })
    }
    load().catch((cause: Error) => { if (!controller.signal.aborted) setError(cause.message) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [experimentId, task, report])
  const grouped = useMemo(() => {
    const groups = new Map<string, Row[]>()
    for (const row of page?.items ?? []) { const key = `${row.item_id}\u0000${row.repetition}\u0000${row.variant}`; groups.set(key, [...(groups.get(key) ?? []), row]) }
    return [...groups.values()].map(group => group.sort((a, b) => a.model_slot - b.model_slot)).filter(group => status === 'all' || group.some(row => row.status === status))
  }, [page, status])
  const current = grouped[questionIndex]
  const noAnswered = summaryCards.length > 0 && summaryCards.every(row=>row.responses===0)
  const allFailed = noAnswered && summaryCards.some(row=>row.failures>0) && summaryCards.every(row=>row.pending===0)
  return <section className="results-panel mt-4 space-y-5 border-t pt-5" aria-labelledby={`results-${experimentId}`}>
    <h3 id={`results-${experimentId}`} className="text-xl font-semibold">Results</h3>
    <p>Compare completion first, then read matching answers and their automatic checks. No overall winner is calculated from this small sample. Speed is separate from answer quality.</p>
    <nav aria-label={`Results sections for experiment ${experimentId}`} className="results-sections"><a href={`#summary-${experimentId}`}>Summary</a><a href={`#answers-${experimentId}`}>Answers</a><a href={`#evaluation-${experimentId}`}>Evaluation details</a><a href={`#exports-${experimentId}`}>Exports</a></nav>
    <section id={`summary-${experimentId}`} aria-labelledby={`summary-title-${experimentId}`}>
      <h4 id={`summary-title-${experimentId}`} className="text-lg font-semibold">Summary</h4>
      <label className="mr-3">Summary model <select className="rounded border p-2" value={model} onChange={event=>setModel(event.target.value)}><option value="all">All models</option>{routeSlots.map(slot=><option key={slot} value={slot}>{routeLabel(slot)}</option>)}</select></label>
      {summaryCards.length === 0 ? <p>No scheduled results for these filters. Choose another task or model.</p> : <div className="route-cards">{summaryCards.map(row => <article className="route-card" key={row.model_slot}>
        <h5>{routeLabel(row.model_slot)}</h5>
        <p><strong>Successful answers:</strong> {row.responses} of {row.scheduled_jobs} scheduled</p>
        <p><strong>Failed / pending / cancelled:</strong> {row.failures} / {row.pending} / {row.cancelled}</p>
        <p><strong>Truncated / malformed / identity mismatch:</strong> {row.truncated} / {row.format_failures} / {row.identity_mismatch}</p>
        {row.responses === 0 && <p className="next-action">No successful answers yet. Check the saved comparison’s errors and paused/worker status before deciding whether to resume. Missing answers are not incorrect answers.</p>}
        <details><summary>Route, speed and token usage</summary>{!hideNames && <p>Exact route: <code>{row.provider} / {row.model_id}</code></p>}<p>Median / p95 successful request time: {show(row.median_request_latency_ms)} / {show(row.p95_request_latency_ms)} ms (n={row.latency_sample_count})</p><p>Reported usage samples: {row.usage_sample_count}; input / output tokens: {show(row.prompt_tokens_total)} / {show(row.completion_tokens_total)}. Unknown usage is not zero.</p></details>
      </article>)}</div>}
      <p>Automatic-check results and eligible-answer denominators are in Evaluation details below; they are not a single overall score.</p>
    </section>
    <section id={`answers-${experimentId}`} aria-labelledby={`answers-title-${experimentId}`}>
      <h4 id={`answers-title-${experimentId}`} className="text-lg font-semibold">Answers side by side</h4>
      <div className="flex flex-wrap gap-3"><label>Task <select className="rounded border p-2" value={task} onChange={event=>setTask(event.target.value)}><option value="all">All tasks</option>{tasks.map(option=><option key={option} value={option}>{option}</option>)}</select></label><label>Metric <select className="rounded border p-2" value={metric} onChange={event=>setMetric(event.target.value)}><option value="all">All metrics</option>{metrics.map(option=><option key={option} value={option}>{metricName(option)}</option>)}</select></label><label>Answer status <select className="rounded border p-2" value={status} onChange={event=>setStatus(event.target.value)}>{['all','answered','malformed','truncated','failed','pending','cancelled'].map(option=><option key={option} value={option}>{option==='all'?'All statuses':metricName(option)}</option>)}</select></label><label><input type="checkbox" checked={hideNames} onChange={event => setHideNames(event.target.checked)} /> Hide model names</label></div>
      {hideNames && <p className="rounded bg-amber-50 p-3">Model and provider identities are hidden in this results view, including snapshot details. A model may identify itself in its answer; this does not blind the answer text. <a className="underline" href="/human-review">Open actual human review</a>.</p>}
      {loading && <p role="status">Loading complete question groups…</p>}{error && <p role="alert">Could not load answers: {error}</p>}
      {!loading && !error && page && grouped.length===0 && <div className="empty-state"><p>{page.total===0?'No question groups are available yet.':'No question groups match this status.'}</p><p>{allFailed?'Next: inspect the experiment’s job errors and worker status; no successful answers were recorded.':summaryCards.length>0&&summaryCards.every(row=>row.responses===0&&row.pending>0)?'Next: check whether the experiment is paused or the worker is running.':'Next: choose another status or check the experiment’s scheduled questions.'}</p></div>}
      {!loading && !error && current && <><div className="flex items-center gap-3" aria-label="Question navigation"><button type="button" className="rounded border px-3 py-2" disabled={questionIndex===0} onClick={()=>setQuestionIndex(questionIndex-1)}>Previous question</button><span>Question {questionIndex+1} of {grouped.length}</span><button type="button" className="rounded border px-3 py-2" disabled={questionIndex+1>=grouped.length} onClick={()=>setQuestionIndex(questionIndex+1)}>Next question</button></div>
        <article className="space-y-3 rounded border p-4"><h5 className="font-semibold">{current[0].task_type} · question {current[0].item_id} · repetition {current[0].repetition} · variant {current[0].variant}</h5><p><strong>Question:</strong> {current[0].prompt}</p>{current[0].context && <p><strong>Reference context:</strong> {current[0].context}</p>}{current[0].choices != null && <p><strong>Choices:</strong> <code>{JSON.stringify(current[0].choices)}</code></p>}<p><strong>Reference answer:</strong> {current[0].reference_answers.join(' | ') || 'No reference answer supplied'}</p>
          <p>{current.filter(row => row.response).length} of {routeSlots.length} models have an answer for this same question, repetition and variant. Check truncation and format warnings before comparing quality.</p>
          <div className="grid gap-3 md:grid-cols-2">{current.map(row=><section key={row.job_id} className="min-w-0 rounded border p-3"><h6 className="font-semibold">{routeLabel(row.model_slot)}</h6>{!hideNames && <details><summary>Exact route identity</summary><code>{row.provider} / {row.model_id}</code></details>}<p>Status: {row.status}{row.attempt_error ? ` · issue: ${row.attempt_error}` : ''}</p>{row.response ? <><pre className="answer-text">{row.response.raw_text || '(empty response)'}</pre>{row.response.truncated && <p role="status">Answer is truncated; it was not scored.</p>}{row.response.identity_mismatch && <p>Returned route identity did not match the selected route.</p>}{row.response.metrics.filter(m=>metric==='all'||m.metric===metric).map((m,i)=><details key={`${m.metric}-${i}`}><summary>{metricName(m.metric)}: {show(m.value)} ({m.parse_status}) · {metricKind(m.metric)}</summary><p>{m.explanation}</p><p>Metric denominator: {show(m.quality_denominator)} eligible answers/checks; scheduled denominator: {show(m.scheduled_denominator)} jobs.</p></details>)}</> : <p>{row.status==='failed'?'The request failed; no answer was recorded.':row.status==='pending'?'This answer is still pending.':'No answer was recorded; missing is not a score.'}</p>}<p className="text-sm">Request time: {show(row.duration_ms)} ms · token use: {row.usage?`${show(row.usage.prompt_tokens)} input / ${show(row.usage.completion_tokens)} output`:'not reported'}</p></section>)}</div>
        </article></>}
    </section>
    <section id={`evaluation-${experimentId}`} aria-labelledby={`evaluation-title-${experimentId}`}><h4 id={`evaluation-title-${experimentId}`} className="text-lg font-semibold">Evaluation details</h4>
      <details><summary>Show automatic-check definitions and saved analysis</summary>
      <p>Deterministic checks apply declared rules to an answer/reference. They measure only that rule, not broad factuality or helpfulness. Proxy measures such as token overlap and ROUGE-L approximate text similarity; they are not human judgments. Request reliability is shown through successful and failed counts; agreement between human reviewers is not measured here.</p>
      <details open><summary>Metric definitions</summary><ul>{metrics.map(name=><li key={name}><strong>{metricName(name)} — {metricKind(name)}:</strong> {metricGuide[name] ?? 'A task-specific scorer result; see the response explanation for its declared rule.'}</li>)}<li><strong>Macro F1 — deterministic aggregate:</strong> unweighted mean of class-wise F1; completed invalid labels count as errors, while missing/truncated items have no confusion entry.</li></ul><p>Completed malformed or unparseable answers receive zero for correctness metrics (and can still have independent parse/schema metrics); missing and truncated answers are null/not scored. Quality denominators include only eligible scored answers, except pooled instruction accuracy, which divides passed declared checks by all declared checks. Binary success divides successful eligible responses by all scheduled jobs.</p></details>
      <h5 className="mt-4 font-medium">Task-specific metric results</h5>
      {rows.length===0 ? <p>No metric rows match these filters. Next: select another model, task, or metric.</p> : <div className="overflow-x-auto"><table className="w-full border-collapse text-left text-sm"><thead><tr>{['Model','Task / metric and type','Quality','Eligible denominator','Scheduled jobs','Classification macro F1','Parse / missing-reference counts'].map(x=><th className="border p-2" key={x}>{x}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={`${r.model_slot}-${r.task_type}-${r.metric}-${i}`}><td className="border p-2">{routeLabel(r.model_slot)}{!hideNames && <details><summary>Exact route</summary><code>{r.provider} / {r.model_id}</code></details>}</td><td className="border p-2">{r.task_type} / {metricName(r.metric)} <span className="metric-badge">{metricKind(r.metric)}</span></td><td className="border p-2">{r.quality===null?'Not available':`${(r.quality*100).toFixed(1)}%`}</td><td className="border p-2">{r.quality_denominator} {r.metric==='instruction_pooled_passed'?'declared checks':'eligible answers'}</td><td className="border p-2">{r.scheduled_jobs}</td><td className="border p-2">{r.metric==='label_accuracy'&&r.macro_f1!==null?r.macro_f1.toFixed(3):'—'}</td><td className="border p-2">Malformed: {r.format_failures} · Missing reference: {r.missing_reference} · Truncated: {r.truncated}</td></tr>)}</tbody></table></div>}
      <div className="space-y-3 rounded border p-3"><h5 className="font-medium">Saved analysis snapshots</h5><p>Snapshots are frozen local paired-family comparisons. They report task metrics separately and do not produce an overall winner. Creating one does not call a model.</p><button type="button" className="rounded border px-3 py-2" disabled={analysisBusy} onClick={createAnalysis}>{analysisBusy?'Saving…':'Save analysis snapshot'}</button>{analyses.length>0 && <label className="ml-3">Snapshot <select className="rounded border p-2" value={analysisId} onChange={event=>setAnalysisId(event.target.value)}>{analyses.map(a=><option key={a.id} value={a.id}>#{a.id} · {a.sha256.slice(0,12)}</option>)}</select></label>}{analysisError && <p role="alert">{analysisError}</p>}{!analyses.length&&!analysisError && <p>No saved snapshots. Next: save one after both models have enough complete paired questions.</p>}{selectedAnalysis && <><p>Snapshot #{selectedAnalysis.id} · SHA-256 <code>{selectedAnalysis.sha256}</code></p><p>Frozen manifest and route identities remain available in the downloaded report.</p><p>Intervals are exploratory and conditional on complete families; omitted answers are not filled in. Fewer than 10 families or missing family metadata may prevent an interval.</p>{selectedAnalysis.results.length===0?<p>No paired metric results in this snapshot.</p>:<div className="overflow-x-auto"><table className="w-full border-collapse text-left text-sm"><thead><tr>{['Task / metric','Complete families','Paired difference (Model B − Model A)','Exploratory 95% interval','Missingness'].map(x=><th className="border p-2" key={x}>{x}</th>)}</tr></thead><tbody>{selectedAnalysis.results.map((r,i)=><tr key={`${r.task_type}-${r.metric}-${i}`}><td className="border p-2">{r.task_type} / {metricName(r.metric)}</td><td className="border p-2">{r.family_n??'Unavailable (family metadata missing)'}</td><td className="border p-2">{r.paired_delta?.toFixed(4)??'Unavailable'}</td><td className="border p-2">{r.interval_95?`${r.interval_95.low.toFixed(4)} to ${r.interval_95.high.toFixed(4)}${r.interval_95.degenerate?' (degenerate: observed family differences are identical)':''}`:'Withheld / unavailable (fewer than 10 complete families or no family metadata)'}</td><td className="border p-2">{r.missing_family_metadata?'Family metadata missing; independent families cannot be inferred':r.omitted_families.length?`${r.omitted_families.length} families omitted`:'No families omitted'}</td></tr>)}</tbody></table></div>}</>}</div>
      </details>
    </section>
    <section id={`exports-${experimentId}`} aria-labelledby={`exports-title-${experimentId}`}><h4 id={`exports-title-${experimentId}`} className="text-lg font-semibold">Exports</h4><p>Download the report in the format you need. A saved snapshot can be included.</p><nav aria-label={`Export experiment ${experimentId}`} className="flex flex-wrap gap-3">{(['csv','json','html','markdown'] as const).map(format=><a key={format} className="rounded border px-3 py-2 underline" href={`/api/experiments/${experimentId}/export?format=${format}`} download={`experiment-${experimentId}.${format}`}>Download {format.toUpperCase()}</a>)}</nav>{selectedAnalysis && <nav aria-label={`Export analysis ${selectedAnalysis.id}`} className="mt-3 flex flex-wrap gap-3">{(['csv','json','html','markdown'] as const).map(format=><a key={format} className="rounded border px-3 py-2 underline" href={`/api/experiments/${experimentId}/export?analysis_id=${encodeURIComponent(selectedAnalysis.id)}&format=${format}`} download={`experiment-${experimentId}-analysis-${selectedAnalysis.id}.${format}`}>Download report + snapshot ({format.toUpperCase()})</a>)}</nav>}</section>
  </section>
}
