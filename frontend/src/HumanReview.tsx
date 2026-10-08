import { useEffect, useState, type FormEvent } from 'react'
import { api } from './Datasets'

type Assignment = {
  opaque_id: string
  mode: 'rubric' | 'pairwise'
  prompt: string
  context: string | null
  choices: unknown
  reference_answers?: unknown
  answers: Record<string, string>
  rubric?: { version: string; anchors: Record<string, Record<string, string>>; transparency_note: string; safety_note: string }
}
type Route = { model_slot: number; provider: string; model_id: string }
type PairSummary = { model_slots: number[]; models: Route[]; wins: Record<string, number>; losses: Record<string, number>; ties: number; cannot_judge: number; count: number; evaluator_count: number; sparse: boolean }
type ReviewSummary = { pairwise: PairSummary[]; rubric: { dimensions: Record<string, { mean: number | null; count: number }>; by_model: Record<string, { route: Route; dimensions: Record<string, { mean: number | null; count: number }>; evaluator_count: number }> } }
const dimensions = ['accuracy', 'relevance', 'fluency', 'transparency', 'safety', 'task_alignment']
const pretty = (name: string) => name.replaceAll('_', ' ')

export default function HumanReview() {
  const [experimentId, setExperimentId] = useState('')
  const [evaluator, setEvaluator] = useState('')
  const [mode, setMode] = useState<'rubric' | 'pairwise'>('pairwise')
  const [includeReferences, setIncludeReferences] = useState(false)
  const [assignment, setAssignment] = useState<Assignment | null>(null)
  const [token, setToken] = useState(() => sessionStorage.getItem('human-review-token') ?? '')
  const [choice, setChoice] = useState('')
  const [identitySuspected, setIdentitySuspected] = useState(false)
  const [scores, setScores] = useState<Record<string, string>>({})
  const [comments, setComments] = useState('')
  const [summary, setSummary] = useState<ReviewSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [submitted, setSubmitted] = useState(() => sessionStorage.getItem('human-review-submitted') === sessionStorage.getItem('human-review-token'))
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    if (!token) return
    let active = true
    setLoading(true); setError(''); setSubmitted(false); setAssignment(null)
    api<Assignment>(`/api/review/assignments/${encodeURIComponent(token)}`)
     .then(value => { if (active) { setAssignment(value); setSubmitted(sessionStorage.getItem('human-review-submitted') === token); setChoice(''); setScores({}); setComments(''); setIdentitySuspected(false) } })
      .catch((cause: Error) => { if (active) setError(`Could not reload assignment: ${cause.message}`) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [token])

  async function create(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice(''); setAssignment(null); sessionStorage.removeItem('human-review-token'); sessionStorage.removeItem('human-review-submitted'); setToken(''); setSubmitted(false)
    try {
      const result = await api<Assignment>('/api/review/assignments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ experiment_id: Number(experimentId), evaluator_label: evaluator, mode, include_references: includeReferences }) })
      setAssignment(result); sessionStorage.setItem('human-review-token', result.opaque_id); setToken(result.opaque_id)
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  async function loadSummary(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setSummary(null)
    try { setSummary(await api<ReviewSummary>(`/api/review/experiments/${encodeURIComponent(experimentId)}/summary`)) }
    catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  async function submit(event: FormEvent) {
    event.preventDefault(); if (!assignment || !token || submitted) return
    setBusy(true); setError(''); setNotice('')
    try {
      const isPairwise = assignment.mode === 'pairwise'
      await api(`/api/review/assignments/${encodeURIComponent(token)}/${isPairwise ? 'vote' : 'rating'}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(isPairwise
          ? { choice, comments: comments || null, identity_suspected: identitySuspected }
          : { scores: Object.fromEntries(dimensions.map(name => [name, scores[name] === '' || scores[name] == null ? null : Number(scores[name])])), comments: comments || null }),
      })
      setSubmitted(true); sessionStorage.setItem('human-review-submitted', token); setNotice('Response saved. This assignment cannot be submitted again.')
    } catch (cause) {
      const message = (cause as Error).message
      setError(message.includes('already') ? `This assignment has already been submitted (409): ${message}` : message)
      if (message.includes('already')) { setSubmitted(true); sessionStorage.setItem('human-review-submitted', token) }
    } finally { setBusy(false) }
  }

  return <section aria-labelledby="review-heading" className="space-y-5">
    <h2 id="review-heading" className="text-xl font-semibold">Human Review</h2>
    <p>Evaluator labels are local labels, not authenticated identities. Responses may self-identify; judge the content as presented and do not edit answer text.</p>
    <form className="space-y-3 border-b pb-5" onSubmit={create}>
      <h3 className="font-semibold">Create assignment</h3>
      <label className="block">Experiment ID <input className="block w-full rounded border p-2" type="number" min="1" step="1" required value={experimentId} onChange={event => setExperimentId(event.target.value)} /></label>
      <label className="block">Evaluator label <input className="block w-full rounded border p-2" maxLength={120} required value={evaluator} onChange={event => setEvaluator(event.target.value)} /></label>
      <label className="block">Mode <select className="block w-full rounded border p-2" value={mode} onChange={event => setMode(event.target.value as 'rubric' | 'pairwise')}><option value="pairwise">Pairwise</option><option value="rubric">Rubric</option></select></label>
      <label className="block"><input type="checkbox" checked={includeReferences} onChange={event => setIncludeReferences(event.target.checked)} /> Include reference answers</label>
      <button className="rounded bg-slate-900 px-3 py-2 text-white disabled:opacity-50" disabled={busy}>{busy ? 'Creating…' : 'Create assignment'}</button>
    </form>
    <form className="space-y-3 border-b pb-5" onSubmit={loadSummary}>
      <h3 className="font-semibold">Review summary</h3>
      <label className="block">Experiment ID <input className="block w-full rounded border p-2" type="number" min="1" step="1" required value={experimentId} onChange={event => setExperimentId(event.target.value)} /></label>
      <button className="rounded border px-3 py-2 disabled:opacity-50" disabled={busy}>{busy ? 'Loading…' : 'Load summary'}</button>
    </form>
    {loading && <p role="status">Reloading active assignment…</p>}
    {error && <p role="alert" className="whitespace-pre-wrap text-red-800">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {assignment && <article className="space-y-4 border-t pt-4">
      <h3 className="font-semibold">{pretty(assignment.mode)} assignment</h3>
      <p><strong>Prompt</strong><br />{assignment.prompt}</p>
      {assignment.context && <p><strong>Context</strong><br /><span className="whitespace-pre-wrap">{assignment.context}</span></p>}
      {assignment.choices != null && <div><strong>Choices</strong><pre className="whitespace-pre-wrap">{JSON.stringify(assignment.choices, null, 2)}</pre></div>}
      {assignment.reference_answers !== undefined && <div><strong>Reference answers</strong><pre className="whitespace-pre-wrap">{JSON.stringify(assignment.reference_answers, null, 2)}</pre></div>}
      <div className="grid gap-4 md:grid-cols-2">{Object.entries(assignment.answers).map(([label, answer]) => <section key={label} className="min-w-0 rounded border p-3"><h4 className="font-semibold">Answer {label}</h4><pre className="whitespace-pre-wrap break-words font-sans">{answer}</pre></section>)}</div>
      <form className="space-y-4" onSubmit={submit}>
        {assignment.mode === 'pairwise' ? <>
          <fieldset className="space-y-2"><legend className="font-semibold">Which answer is better for this task?</legend>
            {[['A', 'A wins'], ['B', 'B wins'], ['tie', 'Tie'], ['cannot_judge', 'Cannot judge']].map(([value, label]) => <label key={value} className="block"><input type="radio" name="pair-choice" required checked={choice === value} onChange={() => setChoice(value)} /> {label}</label>)}
          </fieldset>
          <label className="block"><input type="checkbox" checked={identitySuspected} onChange={event => setIdentitySuspected(event.target.checked)} /> Identity suspected</label>
        </> : <>
          {dimensions.map(name => <fieldset key={name} className="space-y-1 rounded border p-3"><legend className="font-semibold">{pretty(name)}</legend>
            <label className="block">Score <select className="rounded border p-2" value={scores[name] ?? ''} onChange={event => setScores(current => ({ ...current, [name]: event.target.value }))}><option value="">N/A</option>{[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}{n === 2 || n === 4 ? ' (intermediate)' : ''}</option>)}</select></label>
            {(['1', '3', '5'] as const).map(n => <p key={n} className="text-sm"><strong>{n}:</strong> {assignment.rubric?.anchors[name]?.[n]}</p>)}
          </fieldset>)}
          <p>{assignment.rubric?.transparency_note} Transparency does not require chain-of-thought. {assignment.rubric?.safety_note}</p>
        </>}
        <label className="block">Comments <textarea className="block w-full rounded border p-2" maxLength={4000} rows={4} value={comments} onChange={event => setComments(event.target.value)} /></label>
        <button className="rounded bg-slate-900 px-3 py-2 text-white disabled:opacity-50" disabled={busy || submitted || (assignment.mode === 'pairwise' && !choice)}>{submitted ? 'Submitted' : busy ? 'Submitting…' : 'Submit review'}</button>
      </form>
    </article>}
    {summary && <section className="space-y-4 border-t pt-4"><h3 className="font-semibold">Human review aggregates</h3><p>Pairwise preference is not accuracy.</p>
       <h4 className="font-medium">Pairwise preference (not accuracy)</h4>{summary.pairwise.length ? <ul className="list-inside list-disc">{summary.pairwise.map((pair, index) => <li key={pair.model_slots.join('-')}>Comparison {index + 1}: {pair.models.map(route => `${route.provider}/${route.model_id}: ${pair.wins[String(route.model_slot)] ?? 0} wins, ${pair.losses[String(route.model_slot)] ?? 0} losses`).join(' · ')} · ties {pair.ties} · cannot judge {pair.cannot_judge} · comparisons {pair.count} · evaluator labels {pair.evaluator_count}{pair.sparse ? ' · insufficient comparisons (sparse)' : ''}</li>)}</ul> : <p>No pairwise comparisons yet.</p>}
       <h4 className="font-medium">Rubric dimension means by route</h4>{Object.values(summary.rubric.by_model).length ? <ul className="list-inside list-disc">{Object.values(summary.rubric.by_model).map(row=><li key={row.route.model_slot}>{row.route.provider}/{row.route.model_id} (evaluator labels n={row.evaluator_count}): {dimensions.map(name=>`${pretty(name)} ${row.dimensions[name]?.mean == null ? 'N/A' : row.dimensions[name].mean?.toFixed(2)} (n=${row.dimensions[name]?.count ?? 0})`).join(' · ')}</li>)}</ul> : <p>No rubric ratings yet.</p>}
    </section>}
  </section>
}
