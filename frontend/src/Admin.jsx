import { useState, useEffect, useRef } from 'react'
import {
  adminLogin, adminLogout, getAdminConfig, setAdminStyle, toggleFeature,
  uploadKnowledge, deleteKnowledge, addInstruction, updateInstruction,
  deleteInstruction, listKnowledge, getHealth,
  updateVoiceSettings, updateModelSettings, getAdminSessions,
} from './api'

const FEATURE_LABELS = {
  rag_enabled: { label: 'RAG knowledge retrieval', hint: 'Pulls from the knowledge base on explain/compare/objection queries' },
  evaluation_loop_enabled: { label: 'Quality evaluation loop', hint: 'Runs a QC pass and auto-revises weak responses (adds ~1-2s latency)' },
  latency_optimizations_enabled: { label: 'Latency optimizations', hint: 'Streaming progress messages and async tool calls' },
}

const VOICE_BOOL_ROWS = [
  { key: 'output_enabled', label: 'Voice output', hint: 'Speak a summary of each bot response via TTS' },
  { key: 'input_enabled', label: 'Voice input', hint: 'Let users speak instead of type; intent is auto-classified' },
  { key: 'auto_play', label: 'Auto-play', hint: 'Speak immediately after each bot turn (requires output enabled)' },
  { key: 'interruptible', label: 'Interruptible', hint: 'Stop current speech when new input starts' },
]

const VOICE_SELECT_ROWS = [
  { key: 'language', label: 'Language', options: ['english', 'hindi'] },
  { key: 'tone', label: 'Tone', options: ['friendly', 'professional', 'sales'] },
  { key: 'detail_level', label: 'Detail level', options: ['quick', 'moderate', 'detailed'] },
  { key: 'speed', label: 'Speed', options: ['slow', 'normal', 'fast'] },
  { key: 'tts_voice', label: 'TTS Voice', options: ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'] },
]

const TASK_LABELS = {
  chat_agent: 'Chat agent',
  voice_summarizer: 'Voice summariser',
  intent_classifier: 'Intent classifier',
  quality_checker: 'Quality checker',
  document_extraction: 'Document extraction',
}

export default function Admin({ onClose, standalone = false }) {
  const [token, setToken] = useState(() => localStorage.getItem('admin_token') || null)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [config, setConfig] = useState(null)
  const [kbDocs, setKbDocs] = useState([])
  const [kbStats, setKbStats] = useState(null)
  const [newInstruction, setNewInstruction] = useState({ title: '', content: '' })
  const [successMsg, setSuccessMsg] = useState('')
  const [adminAvailable, setAdminAvailable] = useState(true)
  const [appVersion, setAppVersion] = useState('')
  const [taskModelDraft, setTaskModelDraft] = useState({})
  const [sessions, setSessions] = useState(null)
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const fileRef = useRef(null)

  useEffect(() => {
    getHealth().then((h) => {
      setAdminAvailable(h.admin_configured)
      if (h.version) setAppVersion(h.version)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (token) loadAll()
    // eslint-disable-next-line
  }, [token])

  useEffect(() => {
    if (config?.task_models) setTaskModelDraft({ ...config.task_models })
  }, [config?.task_models])

  const flashSuccess = (msg) => {
    setSuccessMsg(msg)
    setTimeout(() => setSuccessMsg(''), 2200)
  }

  const loadAll = async () => {
    try {
      const [cfg, kb] = await Promise.all([getAdminConfig(token), listKnowledge(token)])
      setConfig(cfg)
      setKbDocs(kb.docs)
      setKbStats(kb.stats)
    } catch (err) {
      if (String(err.message).includes('401')) {
        setToken(null)
        sessionStorage.removeItem('admin_token')
      } else {
        setError(err.message)
      }
    }
  }

  const handleLogin = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const t = await adminLogin(password)
      localStorage.setItem('admin_token', t)
      setToken(t)
      setPassword('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = async () => {
    await adminLogout(token)
    localStorage.removeItem('admin_token')
    setToken(null)
    setConfig(null)
    setKbDocs([])
  }

  const loadSessions = async () => {
    setSessionsLoading(true)
    try {
      const data = await getAdminSessions(token)
      setSessions(data.sessions)
    } catch (err) {
      setError(err.message)
    } finally {
      setSessionsLoading(false)
    }
  }

  const handleStyle = async (style) => {
    try {
      const cfg = await setAdminStyle(token, style)
      setConfig(cfg)
      flashSuccess(`Style set to "${style}"`)
    } catch (err) { setError(err.message) }
  }

  const handleToggle = async (feature, enabled) => {
    try {
      const cfg = await toggleFeature(token, feature, enabled)
      setConfig(cfg)
    } catch (err) { setError(err.message) }
  }

  const handleVoiceBool = async (key, value) => {
    try {
      const cfg = await updateVoiceSettings(token, { [key]: value })
      setConfig(cfg)
    } catch (err) { setError(err.message) }
  }

  const handleVoiceSelect = async (key, value) => {
    try {
      const cfg = await updateVoiceSettings(token, { [key]: value })
      setConfig(cfg)
      flashSuccess(`Voice ${key.replace('_', ' ')} set to "${value}"`)
    } catch (err) { setError(err.message) }
  }

  const handleModelFamily = async (family) => {
    try {
      const cfg = await updateModelSettings(token, { model_family: family })
      setConfig(cfg)
      flashSuccess(`Model family switched to ${family} — applies to new sessions`)
    } catch (err) { setError(err.message) }
  }

  const handleTaskModelsSave = async () => {
    try {
      const cfg = await updateModelSettings(token, { task_models: taskModelDraft })
      setConfig(cfg)
      flashSuccess('Task models saved')
    } catch (err) { setError(err.message) }
  }

  const handleUpload = async (file) => {
    if (!file) return
    setLoading(true)
    setError('')
    try {
      await uploadKnowledge(token, file)
      const kb = await listKnowledge(token)
      setKbDocs(kb.docs)
      setKbStats(kb.stats)
      flashSuccess(`Uploaded "${file.name}"`)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const handleDeleteDoc = async (docId) => {
    try {
      await deleteKnowledge(token, docId)
      const kb = await listKnowledge(token)
      setKbDocs(kb.docs)
      setKbStats(kb.stats)
    } catch (err) { setError(err.message) }
  }

  const handleAddInstruction = async () => {
    if (!newInstruction.title.trim() || !newInstruction.content.trim()) return
    try {
      const cfg = await addInstruction(token, newInstruction)
      setConfig(cfg)
      setNewInstruction({ title: '', content: '' })
      flashSuccess('Instruction added')
    } catch (err) { setError(err.message) }
  }

  const handleInstrToggle = async (block) => {
    try {
      const cfg = await updateInstruction(token, block.block_id, { enabled: !block.enabled })
      setConfig(cfg)
    } catch (err) { setError(err.message) }
  }

  const handleInstrDelete = async (blockId) => {
    try {
      const cfg = await deleteInstruction(token, blockId)
      setConfig(cfg)
    } catch (err) { setError(err.message) }
  }

  const handleInstrEdit = async (block, patch) => {
    try {
      const cfg = await updateInstruction(token, block.block_id, patch)
      setConfig(cfg)
    } catch (err) { setError(err.message) }
  }

  // ── Render ─────────────────────────────────────────────────────────

  if (!adminAvailable) {
    return (
      <div className="admin-overlay">
        <div className="admin-header">
          <h2>Admin</h2>
          <button className="admin-close" onClick={onClose}>Close</button>
        </div>
        <div className="admin-body">
          <div className="admin-error">
            Admin mode is not configured. Set the <code>ADMIN_PASSWORD</code> environment
            variable on the server and restart to enable.
          </div>
        </div>
      </div>
    )
  }

  if (!token) {
    return (
      <div className="admin-overlay">
        <div className="admin-header">
          <h2>Admin Login</h2>
          <button className="admin-close" onClick={onClose}>Close</button>
        </div>
        <div className="admin-body">
          <form className="admin-login-form" onSubmit={handleLogin}>
            <label>Admin password</label>
            <input
              type="password"
              className="admin-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
              placeholder="Enter password"
            />
            {error && <div className="admin-error">{error}</div>}
            <div className="admin-row" style={{ marginTop: 16 }}>
              <button className="admin-button" disabled={loading || !password}>
                {loading ? 'Signing in...' : 'Sign in'}
              </button>
            </div>
          </form>
        </div>
      </div>
    )
  }

  if (!config) {
    return (
      <div className="admin-overlay">
        <div className="admin-header"><h2>Admin</h2></div>
        <div className="admin-body">Loading…</div>
      </div>
    )
  }

  const voice = config.voice || {}
  const taskModels = config.task_models || {}
  const taskModelsDirty = JSON.stringify(taskModelDraft) !== JSON.stringify(taskModels)

  return (
    <div className="admin-overlay">
      <div className="admin-header">
        <h2>Admin Panel</h2>
        {appVersion && <span className="admin-version">v{appVersion}</span>}
        <button className="admin-close" onClick={handleLogout}>Logout</button>
        <button className="admin-close" onClick={onClose}>Close</button>
      </div>
      <div className="admin-body">
        {successMsg && <div className="admin-success">{successMsg}</div>}
        {error && <div className="admin-error">{error}</div>}

        {/* Response style */}
        <div className="admin-section">
          <h3>Response Style</h3>
          <div className="style-grid">
            {config.available_styles.map((s) => {
              const preset = s === config.style ? config.style_preset : null
              const active = s === config.style
              return (
                <button
                  key={s}
                  className={`style-option${active ? ' active' : ''}`}
                  onClick={() => handleStyle(s)}
                >
                  <div className="name">{s}</div>
                  <div className="desc">
                    {active && preset ? preset.description : styleHint(s)}
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        {/* Runtime features */}
        <div className="admin-section">
          <h3>Runtime Features</h3>
          {Object.keys(FEATURE_LABELS).map((feat) => (
            <div key={feat} className="toggle-row">
              <div>
                <div className="label">{FEATURE_LABELS[feat].label}</div>
                <div className="hint">{FEATURE_LABELS[feat].hint}</div>
              </div>
              <button
                className={`switch${config[feat] ? ' on' : ''}`}
                onClick={() => handleToggle(feat, !config[feat])}
                aria-label="toggle"
              />
            </div>
          ))}
        </div>

        {/* Voice settings */}
        <div className="admin-section">
          <h3>Voice</h3>
          {VOICE_BOOL_ROWS.map(({ key, label, hint }) => (
            <div key={key} className="toggle-row">
              <div>
                <div className="label">{label}</div>
                <div className="hint">{hint}</div>
              </div>
              <button
                className={`switch${voice[key] ? ' on' : ''}`}
                onClick={() => handleVoiceBool(key, !voice[key])}
                aria-label="toggle"
              />
            </div>
          ))}
          <div className="voice-selects">
            {VOICE_SELECT_ROWS.map(({ key, label, options }) => (
              <div key={key} className="voice-select-row">
                <span className="voice-select-label">{label}</span>
                <div className="voice-option-group">
                  {options.map((opt) => (
                    <button
                      key={opt}
                      className={`voice-option-btn${voice[key] === opt ? ' active' : ''}`}
                      onClick={() => handleVoiceSelect(key, opt)}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Model family */}
        <div className="admin-section">
          <h3>Model Family</h3>
          <div className="hint" style={{ marginBottom: 10, fontSize: 12, color: 'var(--gray-500)' }}>
            Applies to new sessions. Existing sessions keep their current provider until reset.
          </div>
          <div className="voice-option-group" style={{ marginBottom: 16 }}>
            {(config.available_model_families || ['claude', 'openai']).map((fam) => (
              <button
                key={fam}
                className={`voice-option-btn${config.model_family === fam ? ' active' : ''}`}
                onClick={() => handleModelFamily(fam)}
                style={{ textTransform: 'capitalize' }}
              >
                {fam === 'claude' ? '🟣 Claude' : '🟢 OpenAI'}
              </button>
            ))}
          </div>

          <div className="admin-section-sub">
            <div className="label" style={{ marginBottom: 8, fontWeight: 600, fontSize: 12 }}>Per-task models</div>
            {Object.entries(TASK_LABELS).map(([task, label]) => (
              <div key={task} className="task-model-row">
                <span className="task-model-label">{label}</span>
                <input
                  className="task-model-input"
                  value={taskModelDraft[task] || ''}
                  onChange={(e) => setTaskModelDraft((d) => ({ ...d, [task]: e.target.value }))}
                  placeholder={`Model name…`}
                />
              </div>
            ))}
            {taskModelsDirty && (
              <div className="admin-row" style={{ marginTop: 10 }}>
                <button className="admin-button" onClick={handleTaskModelsSave}>Save models</button>
                <button
                  className="admin-button secondary"
                  onClick={() => setTaskModelDraft({ ...taskModels })}
                >
                  Reset
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Knowledge base */}
        <div className="admin-section">
          <h3>Knowledge Base</h3>
          {kbStats && (
            <div className="hint" style={{ marginBottom: 8, fontSize: 12, color: 'var(--gray-500)' }}>
              {kbStats.total_docs} docs · {kbStats.total_chunks} chunks
            </div>
          )}
          <div className="upload-zone" onClick={() => fileRef.current?.click()}>
            <div className="big">📤</div>
            <div><strong>Upload knowledge</strong></div>
            <div style={{ fontSize: 11, marginTop: 4 }}>PDF · DOCX · TXT · MD (max 10 MB)</div>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.doc,.docx,.txt,.md"
            style={{ display: 'none' }}
            onChange={(e) => handleUpload(e.target.files?.[0])}
          />
          <div style={{ marginTop: 12 }}>
            {kbDocs.map((d) => (
              <div key={d.doc_id} className="kb-doc">
                <div className="kb-doc-info">
                  <div className="name">{d.doc_name}</div>
                  <div className="meta">{d.chunks} chunks</div>
                </div>
                <span className={`badge${d.source === 'builtin' ? ' builtin' : ''}`}>
                  {d.source}
                </span>
                {d.source !== 'builtin' && (
                  <button className="remove" onClick={() => handleDeleteDoc(d.doc_id)}>×</button>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Custom instructions */}
        <div className="admin-section">
          <h3>Custom System Instructions</h3>
          {config.custom_instructions.map((b) => (
            <InstructionCard
              key={b.block_id}
              block={b}
              onToggle={() => handleInstrToggle(b)}
              onDelete={() => handleInstrDelete(b.block_id)}
              onEdit={(patch) => handleInstrEdit(b, patch)}
            />
          ))}
          <div className="instruction-card" style={{ borderStyle: 'dashed' }}>
            <div className="top">
              <input
                className="inline-title"
                placeholder="Instruction title"
                value={newInstruction.title}
                onChange={(e) => setNewInstruction((s) => ({ ...s, title: e.target.value }))}
              />
            </div>
            <textarea
              placeholder="e.g. When customer mentions 'EMI', mention our no-cost EMI option on insurance premium."
              value={newInstruction.content}
              onChange={(e) => setNewInstruction((s) => ({ ...s, content: e.target.value }))}
            />
            <div className="admin-row">
              <button
                className="admin-button"
                onClick={handleAddInstruction}
                disabled={!newInstruction.title.trim() || !newInstruction.content.trim()}
              >
                Add instruction
              </button>
            </div>
          </div>
        </div>

        {/* Live sessions */}
        <div className="admin-section">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <h3 style={{ margin: 0 }}>Live Sessions</h3>
            <button className="admin-button secondary" onClick={loadSessions} disabled={sessionsLoading} style={{ fontSize: 11, padding: '4px 10px' }}>
              {sessionsLoading ? 'Loading…' : sessions === null ? 'Load' : 'Refresh'}
            </button>
          </div>
          {sessions === null && !sessionsLoading && (
            <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>Click Load to view active sessions.</div>
          )}
          {sessions && sessions.length === 0 && (
            <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>No active sessions right now.</div>
          )}
          {sessions && sessions.map((s) => (
            <div key={s.session_id} className="session-card">
              <div className="session-header">
                <span className="session-user">
                  {s.user_email ? `${s.user_name || ''} <${s.user_email}>` : 'Anonymous'}
                </span>
                <span className={`session-stage stage-${(s.stage || 'unknown').replace('_', '-')}`}>
                  {s.stage || 'start'}
                </span>
              </div>
              <div className="session-meta">
                <span>💬 {s.message_count} messages</span>
                {s.started_at && (
                  <span>🕐 {new Date(s.started_at).toLocaleTimeString()}</span>
                )}
              </div>
              {s.data_keys.length > 0 && (
                <div className="session-keys">
                  {s.data_keys.map((k) => (
                    <span key={k} className="session-key-badge">{k}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function InstructionCard({ block, onToggle, onDelete, onEdit }) {
  const [title, setTitle] = useState(block.title)
  const [content, setContent] = useState(block.content)
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    setTitle(block.title)
    setContent(block.content)
    setDirty(false)
  }, [block.block_id, block.title, block.content])

  return (
    <div className="instruction-card">
      <div className="top">
        <input
          className="inline-title"
          value={title}
          onChange={(e) => { setTitle(e.target.value); setDirty(true) }}
        />
        <button
          className={`switch${block.enabled ? ' on' : ''}`}
          onClick={onToggle}
          aria-label="toggle"
        />
        <button className="admin-button danger" onClick={onDelete} style={{ padding: '4px 10px', fontSize: 11 }}>
          Delete
        </button>
      </div>
      <textarea
        value={content}
        onChange={(e) => { setContent(e.target.value); setDirty(true) }}
      />
      {dirty && (
        <div className="admin-row">
          <button
            className="admin-button"
            onClick={() => { onEdit({ title, content }); setDirty(false) }}
          >
            Save
          </button>
          <button
            className="admin-button secondary"
            onClick={() => { setTitle(block.title); setContent(block.content); setDirty(false) }}
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  )
}

function styleHint(s) {
  const hints = {
    salesy: 'Warm, urgency-aware, pushes toward conversion.',
    simple: 'Plain, jargon-free, short replies.',
    crisp: 'Professional, bullet-heavy, no fluff.',
    elaborate: 'Deep, educational, explains the why.',
    chatty: 'Casual, empathetic, friend-like tone.',
  }
  return hints[s] || ''
}
