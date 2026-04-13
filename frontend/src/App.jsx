import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const API_URL = '/api'

const WELCOME_SUGGESTIONS = [
  "I want to buy car insurance",
  "My registration number is KA05NG2604",
  "Help me renew my car insurance",
  "What's the cheapest comprehensive plan?",
]

function TypingIndicator() {
  return (
    <div className="message bot">
      <div className="message-avatar">🚗</div>
      <div className="message-content">
        <div className="typing-indicator">
          <div className="typing-dot" />
          <div className="typing-dot" />
          <div className="typing-dot" />
        </div>
      </div>
    </div>
  )
}

function Message({ role, content }) {
  if (role === 'bot') {
    return (
      <div className="message bot">
        <div className="message-avatar">🚗</div>
        <div className="message-content">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
      </div>
    )
  }
  return (
    <div className="message user">
      <div className="message-avatar">👤</div>
      <div className="message-content">{content}</div>
    </div>
  )
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [started, setStarted] = useState(false)
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, loading, scrollToBottom])

  const sendMessage = async (text) => {
    if (!text.trim() || loading) return
    const userMsg = text.trim()
    setInput('')
    setStarted(true)
    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    setLoading(true)

    // Auto-resize textarea back
    if (textareaRef.current) {
      textareaRef.current.style.height = '44px'
    }

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMsg, session_id: sessionId }),
      })

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }

      const data = await res.json()
      setSessionId(data.session_id)
      setMessages(prev => [...prev, { role: 'bot', content: data.response }])
    } catch (err) {
      setMessages(prev => [
        ...prev,
        {
          role: 'bot',
          content: `Sorry, I encountered an error. Please try again. (${err.message})`,
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleReset = async () => {
    if (sessionId) {
      try {
        await fetch(`${API_URL}/reset?session_id=${sessionId}`, { method: 'POST' })
      } catch (_) {}
    }
    setMessages([])
    setSessionId(null)
    setStarted(false)
    setInput('')
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  const handleTextareaChange = (e) => {
    setInput(e.target.value)
    // Auto-resize
    e.target.style.height = '44px'
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
  }

  return (
    <div className="app">
      <div className="header">
        <div className="header-icon">🛡️</div>
        <div className="header-text">
          <h1>Car Insurance Advisor</h1>
          <p>Compare plans from 12+ insurers</p>
        </div>
        <div className="header-actions">
          {started && (
            <button className="reset-btn" onClick={handleReset}>
              New Chat
            </button>
          )}
        </div>
      </div>

      <div className="banner">
        <span className="banner-icon">🎉</span>
        <span>
          <strong>Season Sale:</strong> Up to 20% off on select plans!
        </span>
      </div>

      {!started ? (
        <div className="welcome">
          <div className="welcome-icon">🚗</div>
          <h2>Find the Best Car Insurance</h2>
          <p>
            Compare plans from top insurers, get expert recommendations, and buy
            your policy in minutes.
          </p>
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
          {messages.map((msg, i) => (
            <Message key={i} role={msg.role} content={msg.content} />
          ))}
          {loading && <TypingIndicator />}
          <div ref={messagesEndRef} />
        </div>
      )}

      {!started && (
        <div className="quick-replies">
          {WELCOME_SUGGESTIONS.map((text, i) => (
            <button
              key={i}
              className="quick-reply-btn"
              onClick={() => sendMessage(text)}
            >
              {text}
            </button>
          ))}
        </div>
      )}

      <div className="input-area">
        <div className="input-row">
          <div className="input-wrapper">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              placeholder={
                started
                  ? 'Type your message...'
                  : 'Enter your car registration number...'
              }
              rows={1}
              disabled={loading}
            />
          </div>
          <button
            className="send-btn"
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || loading}
          >
            ➤
          </button>
        </div>
        <div className="powered-by">Powered by Claude AI</div>
      </div>
    </div>
  )
}
