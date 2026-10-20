// Run against the isolated local demo only: node scripts/verify-demo.mjs
import { chromium, expect } from '@playwright/test'
import { mkdir } from 'node:fs/promises'

const baseURL = 'http://127.0.0.1:18202'
const settings = await fetch(`${baseURL}/api/settings`).then(response => response.json())
if (settings.execution_mode !== 'demo') throw new Error('Refusing browser generation outside synthetic demo mode')
const browser = await chromium.launch({ headless: process.env.SHOW_BROWSER !== '1', executablePath: '/usr/bin/chromium', args: ['--no-sandbox'] })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const page = await context.newPage()
const errors = []
page.on('pageerror', error => errors.push(error.message))
page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
page.on('response', response => { if (response.status() >= 500) errors.push(`HTTP ${response.status()}: ${response.url()}`) })
const screenshots = '../docs/screenshots'
await mkdir(screenshots, { recursive: true })
try {
  await page.goto(`${baseURL}/experiments`)
  await page.getByRole('button', { name: 'Continue to models' }).click()
  await page.getByRole('button', { name: 'Refresh provider catalog' }).click()
  const a = page.getByRole('combobox', { name: /^Model A/ })
  const b = page.getByRole('combobox', { name: /^Model B/ })
  await expect(a.locator('option')).toHaveCount(3)
  const values = await a.locator('option').evaluateAll(options => options.map(option => option.value).filter(Boolean))
  await a.selectOption(values[0])
  await b.selectOption(values[1])
  await page.screenshot({ path: `${screenshots}/model-selection-desktop.png`, fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: `${screenshots}/model-selection-mobile.png`, fullPage: true })
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('button', { name: 'Continue to review' }).click()
  await page.getByLabel('Comparison name', { exact: true }).fill('Verified synthetic walkthrough')
  await expect(page.getByRole('button', { name: 'Start comparison', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Start comparison', exact: true }).click()
  await expect(page.getByText('Questions with all answers: 10 of 10', { exact: false }).filter({ visible: true })).toBeVisible({ timeout: 60_000 })
  const results = page.locator('.results-panel').filter({ visible: true })
  await expect(results).toHaveCount(1)
  await expect(results.locator('.answer-text')).toHaveCount(2)
  await results.scrollIntoViewIfNeeded()
  await results.screenshot({ path: `${screenshots}/results-desktop.png` })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await results.evaluate(element => element.scrollIntoView({ block: 'start', behavior: 'instant' }))
  await page.screenshot({ path: `${screenshots}/results-mobile.png` })
  await results.getByRole('checkbox', { name: /Hide model/ }).check()
  await expect(results.getByText('identities are hidden', { exact: false })).toBeVisible()
  await results.getByRole('button', { name: 'Next question' }).click()
  await expect(results.locator('.answer-text')).toHaveCount(2)
  for (const format of ['CSV', 'JSON', 'HTML', 'MARKDOWN']) {
    const download = page.waitForEvent('download')
    await results.getByRole('link', { name: `Download ${format}`, exact: true }).click()
    if (await (await download).failure()) throw new Error(`Failed ${format} download`)
  }
  if (errors.length) throw new Error(errors.join('\n'))
  console.log('PASS: synthetic 20-request comparison, desktop/mobile layout, paired answers, hidden names, four exports; no browser/server errors.')
  console.log(`Screenshots: docs/screenshots/{model-selection,results}-{desktop,mobile}.png`)
} finally {
  await browser.close()
}
