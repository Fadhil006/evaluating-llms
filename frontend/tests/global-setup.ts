import { spawn, spawnSync, type ChildProcess } from 'node:child_process'
import { resolve } from 'node:path'
import type { FullConfig } from '@playwright/test'

const port = '18100'

export default async function globalSetup(_config: FullConfig) {
  const backend = resolve(process.cwd(), '../backend')
  const python = process.env.PYTHON ?? resolve(backend, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python')
  const env = {
    ...process.env,
    EXECUTION_MODE: 'demo',
    DATABASE_PATH: `/tmp/opencode/lclab-e2e-live-${process.pid}.sqlite3`,
    DEMO_DATABASE_PATH: `/tmp/opencode/lclab-e2e-demo-${process.pid}.sqlite3`,
    OPENROUTER_API_KEY: '',
    OPENCODE_ZEN_API_KEY: '',
  }
  const migration = spawnSync(python, ['-m', 'alembic', 'upgrade', 'head'], { cwd: backend, env, encoding: 'utf8' })
  if (migration.status !== 0) throw new Error(`E2E database migration failed:\n${migration.stderr}`)

  const children: ChildProcess[] = []
  const api = spawn(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', port],
    { cwd: backend, env, stdio: 'ignore' })
  children.push(api)
  const worker = spawn(python, ['-m', 'app.worker'], { cwd: backend, env, stdio: 'ignore' })
  children.push(worker)

  try {
    const until = Date.now() + 20_000
    while (Date.now() < until) {
      if (api.exitCode !== null || worker.exitCode !== null) throw new Error('E2E API or worker exited during startup')
      try {
        const response = await fetch(`http://127.0.0.1:${port}/api/health`)
        if (response.ok) return async () => { for (const child of children) child.kill('SIGTERM') }
      } catch { /* Wait for the local API listener. */ }
      await new Promise(resolveWait => setTimeout(resolveWait, 100))
    }
    throw new Error('E2E API did not become healthy')
  } catch (error) {
    for (const child of children) child.kill('SIGTERM')
    throw error
  }
}
