// Real catalog/readiness check only. Never starts or resumes a comparison.
import { chromium, expect } from '@playwright/test'
const base = 'http://127.0.0.1:18202'
const settings = await fetch(`${base}/api/settings`).then(r => r.json())
if (settings.execution_mode !== 'live') throw new Error('Expected live mode')
const models = await fetch(`${base}/api/models`).then(r => r.json())
const ready = models.filter(m => m.eligibility.allowed && m.credential_configured)
const a = ready.find(m => m.provider === 'openrouter' && m.model_id === 'google/gemma-4-31b-it:free') ?? ready.find(m => m.provider === 'openrouter')
const b = ready.find(m => m.provider === 'opencode_zen' && m.model_id === 'big-pickle') ?? ready.find(m => m.provider === 'opencode_zen')
if (!a || !b) throw new Error('Need a ready route from each provider to verify cross-provider selection')
const browser = await chromium.launch({ executablePath: '/usr/bin/chromium', headless: process.env.SHOW_BROWSER !== '1', args: ['--no-sandbox'] })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/experiments**', async route => {
    const path = new URL(route.request().url()).pathname
    if (route.request().method() === 'POST' && path !== '/api/experiments/estimate') {
      errors.push(`Blocked unexpected mutation: ${path}`)
      return route.abort()
    }
    return route.continue()
  })
  await page.goto(`${base}/experiments`)
  await page.getByRole('button', { name: 'Continue to models' }).click()
  await page.getByLabel('Provider filter').selectOption('openrouter')
  await page.getByLabel('Model A', { exact: true }).selectOption(String(a.id))
  await page.getByLabel('Provider filter').selectOption('opencode_zen')
  await page.getByLabel('Model B', { exact: true }).selectOption(String(b.id))
  await page.getByLabel('Provider filter').selectOption('all')
  await expect(page.getByLabel('Model A', { exact: true })).toHaveValue(String(a.id))
  await page.screenshot({ path: '../docs/screenshots/live-model-selection.png', fullPage: true })
  await page.getByRole('button', { name: 'Continue to review' }).click()
  await expect(page.getByRole('button', { name: 'Start comparison', exact: true })).toBeEnabled()
  await expect(page.getByText(/initial generation requests: 20/)).toBeVisible()
  await page.screenshot({ path: '../docs/screenshots/live-review.png', fullPage: true })
  if (errors.length) throw new Error(errors.join('\n'))
  console.log(JSON.stringify({ mode: 'live', readyOpenRouter: ready.filter(m => m.provider === 'openrouter').length,
    readyZen: ready.filter(m => m.provider === 'opencode_zen').length, selectedRoutes: [a.model_id, b.model_id],
    startEnabled: true, generationRequestsSent: 0 }))
} finally { await browser.close() }
