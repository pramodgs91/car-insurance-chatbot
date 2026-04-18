import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { streamChat, uploadDocument, resetSession } from './api'

const INITIAL_SUGGESTIONS = [
  'I want to buy car insurance',
  'My reg is KA05NG2604',
  'Help me renew',
  'What is Zero Depreciation?',
  'Third-party vs Comprehensive',
]

const ACCEPTED_UPLOAD_TYPES = '.pdf,.jpg,.jpeg,.png,.webp,image/*,application/pdf'

function TypingDots() {
  return (
    <div className="typing">
      <div className="typing-dot" />
      <div className="typing-dot" />
      <div className="typing-dot" />
    </div>
  )
}

function ProgressPill({ text, success }) {
  return (
    <div className={`progress-pill${success ? ' success' : ''}`}>
      {!success && <div className="spinner" />}
      {success && <span>✓</span>}
      <span>{text}</span>
    </div>
  )
}

function BotMessage({ content }) {
  return (
    <div className="message bot">
      <div className="message-avatar">🚗</div>
      <div className="message-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    </div>
  )
}

function UserMessage({ content }) {
  return (
    <div className="message user">
      <div className="message-avatar">👤</div>
      <div className="message-content">{content}</div>
    </div>
  )
}

function AttachmentMessage({ name }) {
  return (
    <div className="message user">
      <div className="message-avatar">📎</div>
      <div className="message-content attachment">
        <div className="attachment-name">{name}</div>
        <div className="attachment-hint">Uploaded</div>
      </div>
    </div>
  )
}

export default function Chat({ onOpenAdmin }) {
  const [messages, setMessages] = useState([])
  const [progressEvents, setProgressEvents] = useState([])
  const [streamingText, setStreamingText] = useState('')
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [ux, setUx] = useState(null)
  const [multiSelection, setMultiSelection] = useState([])
  const [started, setStarted] = useState(false)

  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, progressEvents, streamingText, loading, scrollToBottom])

  // ── Shared SSE event handler ───────────────────────────────────────
  const handleEvent = (evt) => {
    if (evt.type === 'session') {
      setSessionId(evt.session_id)
    } else if (evt.type === 'progress' || evt.type === 'tool_start') {
      setProgressEvents((p) => [
        ...p,
        { text: evt.text, done: false, id: Date.now() + Math.random() },
      ])
    } else if (evt.type === 'tool_end') {
      setProgressEvents((p) =>
        p.length > 0 ? [...p.slice(0, -1), { ...p[p.length - 1], done: true }] : p
      )
    } else if (evt.type === 'token') {
      setProgressEvents([])
      setStreamingText((t) => t + (evt.text || ''))
    } else if (evt.type === 'token_reset') {
      setStreamingText('')
    } else if (evt.type === 'final') {
      setProgressEvents([])
      setStreamingText('')
      setMessages((m) => [...m, { role: 'bot', content: evt.text }])
      setUx(evt.ux || null)
    } else if (evt.type === 'error') {
      setProgressEvents([])
      setStreamingText('')
      setMessages((m) => [
        ...m,
        { role: 'bot', content: `Sorry, something went wrong: ${evt.text}` },
      ])
    }
  }

  // ── Text send ─────────────────────────────────────────────────────
  const send = async (text) => {
    const msg = (text || '').trim()
    if (!msg || loading) return
    setStarted(true)
    setInput('')
    setUx(null)
    setMultiSelection([])
    setMessages((m) => [...m, { role: 'user', content: msg }])
    setProgressEvents([])
    setStreamingText('')
    setLoading(true)

    if (textareaRef.current) textareaRef.current.style.height = '44px'

    try {
      await streamChat({ message: msg, sessionId, onEvent: handleEvent })
    } catch (err) {
      setMessages((m) => [...m, { role: 'bot', content: `Network error: ${err.message}` }])
    } finally {
      setLoading(false)
    }
  }

  // ── File upload ───────────────────────────────────────────────────
  const triggerFilePicker = () => {
    if (loading) return
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = '' // allow re-upload of same filename later
    if (!file) return
    if (file.size > 10 * 1024 * 1024) {
      setMessages((m) => [
        ...m,
        { role: 'bot', content: 'That file is larger than 10 MB. Please compress or try a different one.' },
      ])
      return
    }

    setStarted(true)
    setUx(null)
    setMultiSelection([])
    setMessages((m) => [...m, { role: 'attachment', content: file.name }])
    setProgressEvents([])
    setStreamingText('')
    setLoading(true)

    try {
      await uploadDocument({ file, sessionId, onEvent: handleEvent })
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: 'bot', content: `Couldn't upload: ${err.message}` },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleReset = async () => {
    await resetSession(sessionId)
    setMessages([])
    setSessionId(null)
    setStarted(false)
    setInput('')
    setUx(null)
    setProgressEvents([])
    setStreamingText('')
    setMultiSelection([])
  }

  const handleChoiceClick = (opt) => send(opt.label)

  const handleMultiToggle = (opt) => {
    setMultiSelection((cur) => {
      const exists = cur.find((x) => x.value === opt.value)
      return exists ? cur.filter((x) => x.value !== opt.value) : [...cur, opt]
    })
  }

  const handleMultiApply = () => {
    if (!multiSelection.length) {
      send('Skip add-ons for now')
      return
    }
    const labels = multiSelection.map((x) => x.label).join(', ')
    send(`Add these: ${labels}`)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send(input)
    }
  }

  const handleTextareaChange = (e) => {
    setInput(e.target.value)
    e.target.style.height = '44px'
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
  }

  // A suggestion labelled like an upload prompt should open the file
  // picker instead of sending the literal text.
  const isUploadSuggestion = (label) =>
    typeof label === 'string' && /upload|rc card|policy.*pdf|document/i.test(label)

  const handleSuggestion = (label) => {
    if (isUploadSuggestion(label)) triggerFilePicker()
    else send(label)
  }

  const renderInteractive = () => {
    const suggestions = ux?.suggestions
    const inputSpec = ux?.input
    const hasStructured =
      inputSpec &&
      (inputSpec.type === 'choice' || inputSpec.type === 'multi_choice') &&
      Array.isArray(inputSpec.options) &&
      inputSpec.options.length > 0

    if (!started) {
      return (
        <div className="interactive-zone">
          <div className="suggestions scroll-row">
            <button className="chip upload-chip" onClick={triggerFilePicker}>
              📎 Upload RC or policy
            </button>
            {INITIAL_SUGGESTIONS.map((t) => (
              <button key={t} className="chip" onClick={() => send(t)}>{t}</button>
            ))}
          </div>
        </div>
      )
    }

    if (!suggestions && !hasStructured) return null

    return (
      <div className="interactive-zone">
        {hasStructured && inputSpec.type === 'choice' && (
          <div className="structured-input scroll-row">
            {inputSpec.options.map((o) => (
              <button key={o.value} className="chip choice" onClick={() => handleChoiceClick(o)}>
                {o.label}
              </button>
            ))}
          </div>
        )}
        {hasStructured && inputSpec.type === 'multi_choice' && (
          <>
            <div className="structured-input scroll-row">
              {inputSpec.options.map((o) => {
                const selected = multiSelection.some((x) => x.value === o.value)
                return (
                  <button
                    key={o.value}
                    className={`chip choice${selected ? ' selected' : ''}`}
                    onClick={() => handleMultiToggle(o)}
                  >
                    {selected ? '✓ ' : ''}{o.label}
                  </button>
                )
              })}
            </div>
            <div className="multi-apply-row">
              <button onClick={handleMultiApply} disabled={loading}>
                {multiSelection.length > 0
                  ? `Continue with ${multiSelection.length} selected`
                  : 'Skip for now'}
              </button>
            </div>
          </>
        )}
        {suggestions && suggestions.length > 0 && !hasStructured && (
          <div className="suggestions scroll-row">
            {suggestions.map((s) => (
              <button key={s} className={`chip${isUploadSuggestion(s) ? ' upload-chip' : ''}`} onClick={() => handleSuggestion(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <>
      <div className="header">
        <div className="header-icon">🛡️</div>
        <div className="header-text">
          <h1>Insurance Advisor</h1>
        </div>
        <div className="header-actions">
          {started && (
            <button className="header-btn" onClick={handleReset}>New chat</button>
          )}
          <button className="header-btn" onClick={onOpenAdmin}>Admin</button>
        </div>
      </div>

      <div className="banner">
        <span>🎉</span>
        <span><strong>Season Sale:</strong> Up to 20% off on select plans</span>
      </div>

      {!started ? (
        <div className="welcome">
          <div className="welcome-icon">🚗</div>
          <h2>Find the Best Car Insurance</h2>
          <p>Upload your RC card or previous policy — or just enter your registration number — and we'll do the rest.</p>
          <button className="welcome-upload-cta" onClick={triggerFilePicker}>
            <span>📎</span>
            <span>Upload RC or Policy</span>
          </button>
          <div className="welcome-or">or type to start below</div>
        </div>
      ) : (
        <div className="messages">
          {messages.map((m, i) => {
            if (m.role === 'bot') return <BotMessage key={i} content={m.content} />
            if (m.role === 'attachment') return <AttachmentMessage key={i} name={m.content} />
            return <UserMessage key={i} content={m.content} />
          })}
          {progressEvents.map((p) => (
            <ProgressPill key={p.id} text={p.text} success={p.done} />
          ))}
          {streamingText && <BotMessage content={streamingText} />}
          {loading && progressEvents.length === 0 && !streamingText && <TypingDots />}
          <div ref={messagesEndRef} />
        </div>
      )}

      {renderInteractive()}

      <div className="input-area">
        <div className="input-row">
          <button
            className="attach-btn"
            onClick={triggerFilePicker}
            disabled={loading}
            aria-label="Attach file"
            title="Upload RC card or policy"
          >
            📎
          </button>
          <div className="input-wrapper">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              placeholder={started ? 'Type your message...' : 'Enter your car registration number...'}
              rows={1}
              disabled={loading}
            />
          </div>
          <button
            className="send-btn"
            onClick={() => send(input)}
            disabled={!input.trim() || loading}
            aria-label="Send"
          >
            ➤
          </button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_UPLOAD_TYPES}
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
      </div>
    </>
  )
}
