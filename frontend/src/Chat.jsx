import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { streamChat, resetSession } from './api'

const INITIAL_SUGGESTIONS = [
  'I want to buy car insurance',
  'My registration is KA05NG2604',
  'Help me renew my policy',
  'What is Zero Depreciation?',
]

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

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    })
  }, [])

  useEffect(() => { scrollToBottom() }, [messages, progressEvents, streamingText, loading, scrollToBottom])

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
      await streamChat({
        message: msg,
        sessionId,
        onEvent: (evt) => {
          if (evt.type === 'session') {
            setSessionId(evt.session_id)
          } else if (evt.type === 'progress' || evt.type === 'tool_start') {
            setProgressEvents((p) => [...p, { text: evt.text, done: false, id: Date.now() + Math.random() }])
          } else if (evt.type === 'tool_end') {
            setProgressEvents((p) =>
              p.length > 0 ? [...p.slice(0, -1), { ...p[p.length - 1], done: true }] : p
            )
          } else if (evt.type === 'token') {
            // Clear pills once actual text starts arriving.
            setProgressEvents([])
            setStreamingText((t) => t + (evt.text || ''))
          } else if (evt.type === 'token_reset') {
            // Model went into a tool call / revision — discard what we've shown.
            setStreamingText('')
          } else if (evt.type === 'final') {
            setProgressEvents([])
            setStreamingText('')
            setMessages((m) => [...m, { role: 'bot', content: evt.text }])
            setUx(evt.ux || null)
          } else if (evt.type === 'error') {
            setProgressEvents([])
            setStreamingText('')
            setMessages((m) => [...m, { role: 'bot', content: `Sorry, something went wrong: ${evt.text}` }])
          }
        },
      })
    } catch (err) {
      setMessages((m) => [...m, { role: 'bot', content: `Network error: ${err.message}` }])
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

  const handleChoiceClick = (opt) => {
    send(opt.label)
  }

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
          <div className="suggestions">
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
          <div className="structured-input">
            {inputSpec.options.map((o) => (
              <button key={o.value} className="chip choice" onClick={() => handleChoiceClick(o)}>
                {o.label}
              </button>
            ))}
          </div>
        )}
        {hasStructured && inputSpec.type === 'multi_choice' && (
          <>
            <div className="structured-input">
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
                {multiSelection.length > 0 ? `Continue with ${multiSelection.length} selected` : 'Skip for now'}
              </button>
            </div>
          </>
        )}
        {suggestions && suggestions.length > 0 && !hasStructured && (
          <div className="suggestions">
            {suggestions.map((s) => (
              <button key={s} className="chip" onClick={() => send(s)}>{s}</button>
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
          <h1>Car Insurance Advisor</h1>
          <p>Compare plans from 12+ insurers</p>
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
          <p>Compare plans from top insurers, get expert recommendations, and buy your policy in minutes.</p>
          <div className="welcome-features">
            <div className="feature-card">
              <span className="feature-icon">🔍</span>
              <div className="feature-text">
                <strong>Instant Lookup</strong>
                Enter your registration number to get started
              </div>
            </div>
            <div className="feature-card">
              <span className="feature-icon">📊</span>
              <div className="feature-text">
                <strong>Compare Plans</strong>
                Side-by-side comparison from 12+ insurers
              </div>
            </div>
            <div className="feature-card">
              <span className="feature-icon">💰</span>
              <div className="feature-text">
                <strong>Best Prices</strong>
                Exclusive discounts and NCB benefits
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="messages">
          {messages.map((m, i) =>
            m.role === 'bot' ? <BotMessage key={i} content={m.content} /> : <UserMessage key={i} content={m.content} />
          )}
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
        <div className="powered-by">Powered by Claude AI</div>
      </div>
    </>
  )
}
