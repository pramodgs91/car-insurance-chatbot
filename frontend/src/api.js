// Centralized API client. Handles streaming chat, session, and admin.

const API_BASE = '/api'

export async function resetSession(sessionId) {
  if (!sessionId) return
  try {
    await fetch(`${API_BASE}/reset?session_id=${sessionId}`, { method: 'POST' })
  } catch {}
}

/**
 * Stream a chat turn via SSE. Calls `onEvent({type, ...})` for each event.
 * Returns a Promise that resolves when the stream ends (after 'final' or 'error').
 */
export async function streamChat({ message, sessionId, onEvent, signal }) {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
    signal,
  })
  if (!res.ok || !res.body) {
    throw new Error(`Stream failed: HTTP ${res.status}`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE events are separated by a blank line
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''
    for (const part of parts) {
      if (!part.trim()) continue
      let eventType = 'message'
      let dataLine = ''
      for (const line of part.split('\n')) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim()
        else if (line.startsWith('data: ')) dataLine = line.slice(6)
      }
      if (!dataLine) continue
      let data
      try { data = JSON.parse(dataLine) } catch { continue }
      onEvent({ type: eventType, ...data })
      if (eventType === 'final' || eventType === 'error') return
    }
  }
}

// ── Admin ────────────────────────────────────────────────────────────────

function adminHeaders(token) {
  return token ? { 'X-Admin-Token': token } : {}
}

export async function adminLogin(password) {
  const res = await fetch(`${API_BASE}/admin/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Login failed (${res.status})`)
  }
  const { token } = await res.json()
  return token
}

export async function adminLogout(token) {
  try {
    await fetch(`${API_BASE}/admin/logout`, {
      method: 'POST',
      headers: adminHeaders(token),
    })
  } catch {}
}

export async function getAdminConfig(token) {
  const res = await fetch(`${API_BASE}/admin/config`, { headers: adminHeaders(token) })
  if (!res.ok) throw new Error(`Config fetch failed (${res.status})`)
  return res.json()
}

export async function setAdminStyle(token, style) {
  const res = await fetch(`${API_BASE}/admin/style`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...adminHeaders(token) },
    body: JSON.stringify({ style }),
  })
  if (!res.ok) throw new Error(`Style change failed (${res.status})`)
  return res.json()
}

export async function toggleFeature(token, feature, enabled) {
  const res = await fetch(`${API_BASE}/admin/feature`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...adminHeaders(token) },
    body: JSON.stringify({ feature, enabled }),
  })
  if (!res.ok) throw new Error(`Toggle failed (${res.status})`)
  return res.json()
}

export async function listKnowledge(token) {
  const res = await fetch(`${API_BASE}/admin/knowledge`, { headers: adminHeaders(token) })
  if (!res.ok) throw new Error(`KB fetch failed (${res.status})`)
  return res.json()
}

export async function uploadKnowledge(token, file) {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${API_BASE}/admin/knowledge/upload`, {
    method: 'POST',
    headers: adminHeaders(token),
    body: fd,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Upload failed (${res.status})`)
  }
  return res.json()
}

export async function deleteKnowledge(token, docId) {
  const res = await fetch(`${API_BASE}/admin/knowledge/${docId}`, {
    method: 'DELETE',
    headers: adminHeaders(token),
  })
  if (!res.ok) throw new Error(`Delete failed (${res.status})`)
  return res.json()
}

export async function addInstruction(token, { title, content, enabled = true }) {
  const res = await fetch(`${API_BASE}/admin/instructions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...adminHeaders(token) },
    body: JSON.stringify({ title, content, enabled }),
  })
  if (!res.ok) throw new Error(`Add instruction failed (${res.status})`)
  return res.json()
}

export async function updateInstruction(token, blockId, patch) {
  const res = await fetch(`${API_BASE}/admin/instructions/${blockId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...adminHeaders(token) },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(`Update failed (${res.status})`)
  return res.json()
}

export async function deleteInstruction(token, blockId) {
  const res = await fetch(`${API_BASE}/admin/instructions/${blockId}`, {
    method: 'DELETE',
    headers: adminHeaders(token),
  })
  if (!res.ok) throw new Error(`Delete failed (${res.status})`)
  return res.json()
}

export async function getHealth() {
  const res = await fetch(`${API_BASE}/health`)
  return res.json()
}
