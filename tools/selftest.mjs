/**
 * Offline self-test for the vidlens DSH plugin.
 *
 *   node tools/selftest.mjs
 *
 * Checks the two halves independently of the Harness:
 *   1. the tool table the Host will register (names, schemas, descriptions);
 *   2. the Python bridge: boot handshake + three cache-only tools (library,
 *      models, seek). No network, no media download.
 */

import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(HERE, '..')

const results = []
const ok = (label, extra = '') => results.push({ pass: true, label, extra })
const bad = (label, extra = '') => results.push({ pass: false, label, extra })

function assert(label, condition, extra = '') {
  if (condition) ok(label, extra)
  else bad(label, extra)
}

// ------------------------------------------------------------------ 1. tools
const mod = await import(pathToFileURL(path.join(ROOT, 'index.js')).href)
const tools = mod.__internals.TOOLS
assert('index.js exports apply()', typeof mod.apply === 'function')
assert('index.js exports inject=[tools]', JSON.stringify(mod.inject) === '["tools"]')
assert('tool count >= 17', tools.length >= 17, `${tools.length} tools`)

const names = new Set()
for (const t of tools) {
  assert(`${t.name}: unique`, !names.has(t.name))
  names.add(t.name)
  assert(`${t.name}: parameters is an object schema`,
    t.parameters && t.parameters.type === 'object' && t.parameters.properties,
    JSON.stringify(t.parameters || {}).slice(0, 120))
  assert(`${t.name}: description >= 30 chars`, String(t.description || '').length >= 30)
  assert(`${t.name}: has a deadline`, Number(t.timeoutMs) > 0, `${t.timeoutMs}ms`)
  for (const req of t.parameters.required || []) {
    assert(`${t.name}: required '${req}' is declared`, !!t.parameters.properties[req])
  }
}
assert('prompt section mentions the sampling order', /vidlens_meta/.test(mod.__internals.PROMPT))

// -------------------------------------------------------------- 2. python side
const project = process.env.VIDLENS_PROJECT || path.resolve(ROOT, '..', 'vidlens')
const candidates = [
  process.env.VIDLENS_PYTHON,
  path.join(project, '.venv', 'Scripts', 'python.exe'),
  path.join(project, '.venv', 'bin', 'python'),
].filter(Boolean)
const python = candidates.find((p) => existsSync(p)) || (process.platform === 'win32' ? 'python' : 'python3')

assert('vidlens project detected', existsSync(path.join(project, 'vidlens.py')), project)

const child = spawn(python, ['-u', path.join(ROOT, 'bridge', 'vidlens_bridge.py')], {
  cwd: project,
  env: { ...process.env, PYTHONIOENCODING: 'utf-8', VIDLENS_PROJECT: project },
  windowsHide: true,
  stdio: ['pipe', 'pipe', 'pipe'],
})

let buffer = ''
const waiters = new Map()
let ready = null
let seq = 0
let stderr = ''

child.stdout.setEncoding('utf8')
child.stderr.setEncoding('utf8')
child.stderr.on('data', (d) => { stderr = (stderr + d).slice(-4000) })
child.stdout.on('data', (chunk) => {
  buffer += chunk
  let at
  while ((at = buffer.indexOf('\n')) >= 0) {
    const line = buffer.slice(0, at)
    buffer = buffer.slice(at + 1)
    if (!line.trim()) continue
    let msg
    try { msg = JSON.parse(line) } catch { bad('bridge stdout is JSON only', line.slice(0, 200)); continue }
    if (msg.op === 'ready') { ready = msg; continue }
    const w = waiters.get(msg.id)
    if (!w) continue
    waiters.delete(msg.id)
    msg.ok ? w.resolve(msg) : w.reject(new Error(msg.error))
  }
})

function call(tool, args = {}, timeoutMs = 120_000) {
  return new Promise((resolve, reject) => {
    const id = ++seq
    const timer = setTimeout(() => { waiters.delete(id); reject(new Error(`${tool} 超时`)) }, timeoutMs)
    waiters.set(id, {
      resolve: (v) => { clearTimeout(timer); resolve(v) },
      reject: (e) => { clearTimeout(timer); reject(e) },
    })
    child.stdin.write(JSON.stringify({ id, tool, args }) + '\n')
  })
}

const bootDeadline = Date.now() + 60_000
while (!ready && child.exitCode === null && Date.now() < bootDeadline) {
  await new Promise((r) => setTimeout(r, 100))
}
assert('bridge boot handshake', !!ready, ready ? `py ${ready.python} @ ${ready.project}` : stderr.slice(-500))
assert('bridge imported vidlens', !!ready?.ok, ready?.error || '')
assert('bridge exposes every tool the Host registers',
  tools.filter((t) => !t.local).every((t) => (ready?.tools || []).includes(t.bridge)),
  `missing: ${tools.filter((t) => !t.local).map((t) => t.bridge).filter((b) => !(ready?.tools || []).includes(b)).join(',')}`)

try {
  const library = await call('library', { limit: 3 })
  assert('vidlens_library answers', typeof library.text === 'string' && library.text.length > 10,
    library.text.split('\n')[0])

  const models = await call('models', { action: 'list' })
  assert('vidlens_models answers', /模型目录|本地模型/.test(models.text || ''),
    (models.text || '').split('\n')[0])

  const seek = await call('seek', { query: '的', limit: 3 })
  const seekText = String(seek.text || '')
  assert('vidlens_seek answers', seekText.includes('匹配') || seekText.startsWith('# 没查到'),
    seekText.split('\n')[0])

  const missing = await call('seek', {})
  assert('bad args return a readable error', /ERROR/.test(missing.text || missing.error || ''),
    String(missing.text || missing.error).slice(0, 80))

  // Worker resilience: a cancelled/timed-out call kills the worker, so the next
  // call must transparently respawn it.
  const owned = new mod.__internals.Bridge({ python, project })
  try {
    const before = await owned.call({ tool: 'models', args: {} }, { timeoutMs: 60_000 })
    owned.kill('selftest forced kill')
    const after = await owned.call({ tool: 'models', args: {} }, { timeoutMs: 60_000 })
    assert('bridge respawns after a forced kill',
      typeof before.text === 'string' && typeof after.text === 'string' && after.text.length > 10,
      after.text.split('\n')[0])
  } catch (err) {
    bad('bridge respawns after a forced kill', String(err?.message || err))
  } finally {
    owned.dispose()
  }

  // Optional live probe: exercises the kwargs path into `vl_mcp` and the image
  // channel end to end. `node tools/selftest.mjs --live` (~1MB of media).
  if (process.argv.includes('--live')) {
    const firstId = (String(library.text || '').match(/`(BV[0-9A-Za-z]{10})`/) || [])[1]
    const url = process.env.VIDLENS_LIVE_URL
      || (firstId ? `https://www.bilibili.com/video/${firstId}` : 'https://www.youtube.com/watch?v=aqz-KE-bpKQ')
    const meta = await call('meta', { url }, 180_000)
    assert('live vidlens_meta', /时长:/.test(meta.text || ''), (meta.text || '').split('\n')[2] || url)

    const sheet = await call('sheet', { url, start: '0', end: '12', cols: 3, rows: 2 }, 300_000)
    assert('live vidlens_sheet returns an image',
      (sheet.images || []).length >= 1,
      (sheet.images || []).map((i) => `${i.name} ${i.mediaType}`).join(', ') || (sheet.text || '').slice(0, 120))
    if (sheet.images?.[0]) {
      assert('sheet image file exists', existsSync(sheet.images[0].path), sheet.images[0].path)
    }

    const scape = await call('soundscape', { url, start: '0', end: '20' }, 300_000)
    const scapeText = String(scape.text || '')
    assert('live vidlens_soundscape answers',
      scapeText.includes('声音景观') || scapeText.includes('未安装音频事件模型'),
      scapeText.split('\n')[0])
  }
} catch (err) {
  bad('bridge tool calls', String(err?.message || err))
}

child.kill()

// -------------------------------------------------------------------- report
let failed = 0
for (const r of results) {
  if (!r.pass) failed += 1
  const mark = r.pass ? 'PASS' : 'FAIL'
  console.log(`${mark}  ${r.label}${r.extra ? '  —  ' + r.extra : ''}`)
}
console.log(`\n${results.length - failed}/${results.length} checks passed`)
process.exit(failed ? 1 : 0)
