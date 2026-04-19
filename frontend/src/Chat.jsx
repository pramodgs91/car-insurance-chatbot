import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  streamChat,
  uploadDocument,
  resetSession,
  getPublicRuntimeConfig,
  getVoiceGuide,
  classifyVoiceIntent,
} from './api'
import GoogleSignIn from './GoogleSignIn'

const INITIAL_SUGGESTIONS = [
  'I want to buy car insurance',
  'My reg is KA05NG2604',
  'Help me renew',
  'What is Zero Depreciation?',
  'Third-party vs Comprehensive',
]

const ACCEPTED_UPLOAD_TYPES = '.pdf,.jpg,.jpeg,.png,.webp,image/*,application/pdf'
const SPEED_RATES = { slow: 0.9, normal: 1, fast: 1.12 }

// ── Logomark SVG ──────────────────────────────────────────────────────
function Logomark({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" aria-hidden="true">
      <defs>
        <linearGradient id="logoG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--accent)" />
          <stop offset="1" stopColor="var(--accent)" stopOpacity="0.3" />
        </linearGradient>
      </defs>
      <circle cx="14" cy="14" r="13" fill="none" stroke="var(--ink-mute)" strokeWidth="0.7" />
      <path d="M3 16 Q 14 9 25 16" fill="none" stroke="url(#logoG)" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="14" cy="12" r="2.6" fill="var(--accent)" />
    </svg>
  )
}

// ── Car silhouette SVG ────────────────────────────────────────────────
function CarSilhouette() {
  return (
    <svg viewBox="0 0 240 150" width="100%" height="100%" aria-hidden="true">
      <defs>
        <linearGradient id="bodyG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--panel-hi)" />
          <stop offset="1" stopColor="var(--bg)" />
        </linearGradient>
        <linearGradient id="windowG" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="var(--accent)" stopOpacity="0.35" />
          <stop offset="1" stopColor="var(--accent)" stopOpacity="0.05" />
        </linearGradient>
      </defs>
      <ellipse cx="120" cy="128" rx="110" ry="6" fill="var(--accent)" opacity="0.12" />
      <path
        d="M18 110 Q 22 88 48 82 L 78 60 Q 96 48 126 48 L 168 48 Q 188 50 206 70 L 222 88 Q 228 96 228 108 L 228 118 Q 228 122 224 122 L 20 122 Q 16 122 16 118 Z"
        fill="url(#bodyG)" stroke="var(--accent)" strokeOpacity="0.4" strokeWidth="0.8"
      />
      <path d="M82 66 Q 98 56 124 56 L 164 56 Q 180 58 194 74 L 200 86 L 72 86 Z" fill="url(#windowG)" />
      <path d="M132 58 L 136 86" stroke="var(--line)" strokeWidth="1" />
      <circle cx="150" cy="102" r="1" fill="var(--accent)" />
      <circle cx="96"  cy="102" r="1" fill="var(--accent)" />
      <circle cx="68"  cy="118" r="15" fill="var(--bg)"    stroke="var(--ink)" strokeOpacity="0.2" strokeWidth="1" />
      <circle cx="68"  cy="118" r="7"  fill="var(--panel)" stroke="var(--accent)" strokeOpacity="0.5" />
      <circle cx="184" cy="118" r="15" fill="var(--bg)"    stroke="var(--ink)" strokeOpacity="0.2" strokeWidth="1" />
      <circle cx="184" cy="118" r="7"  fill="var(--panel)" stroke="var(--accent)" strokeOpacity="0.5" />
      <circle cx="220" cy="95" r="12" fill="var(--accent)" opacity="0.18" />
      <circle cx="220" cy="95" r="3"  fill="var(--accent)" />
    </svg>
  )
}

// ── Rich card: vehicle found ──────────────────────────────────────────
function CarFoundCard({ reg, make, model, year }) {
  return (
    <div className="card-vehicle">
      <div className="card-car-art">
        <CarSilhouette />
      </div>
      <div className="card-eyebrow">
        <span className="dot-ok" /> Vehicle found
      </div>
      <h3 className="card-headline">{year} {make}</h3>
      <p className="card-sub">{model}</p>
      <div className="card-foot">
        <span className="reg-plate">{reg}</span>
        <span className="card-meta">Petrol · 1.2L</span>
      </div>
    </div>
  )
}

// ── Rich card: plan selector ──────────────────────────────────────────
const PLANS = [
  {
    id: 'lite', name: 'Lite', tag: 'The essentials',
    price: 6420, cover: '3rd-party liability',
    color: 'var(--ink-soft)',
  },
  {
    id: 'comp', name: 'Complete', tag: 'Recommended for you',
    price: 11980, cover: 'Own damage + 3rd party',
    color: 'var(--accent)', highlight: true,
  },
  {
    id: 'pro', name: 'Shield Pro', tag: 'Peace of mind, fully',
    price: 16240, cover: 'Zero dep + engine + RSA',
    color: 'var(--ok)',
  },
]

function PlanCards({ onSelect }) {
  const [selected, setSelected] = useState(null)
  return (
    <div className="plan-cards-wrap">
      {PLANS.map((p, i) => {
        const active = selected === p.id
        return (
          <button
            key={p.id}
            className={`plan-card${active ? ' active' : ''}`}
            style={{ animationDelay: `${0.05 + i * 0.08}s` }}
            onClick={() => { setSelected(p.id); onSelect?.(p) }}
          >
            {p.highlight && <div className="plan-card-best-fit">★ BEST FIT</div>}
            <div className="plan-card-tag">
              <span className="plan-card-dot" style={{ background: p.color }} />
              <span style={{ color: p.color }}>{p.tag}</span>
            </div>
            <div className="plan-card-row">
              <div className="plan-card-name">{p.name}</div>
              <div className="plan-card-price">
                <span className="price-curr">₹</span>
                {p.price.toLocaleString('en-IN')}
                <span className="price-freq">/yr</span>
              </div>
            </div>
            <div className="plan-card-cover">{p.cover}</div>
            {active && (
              <div className="plan-card-features">
                {['Zero paperwork', 'Cashless @ 6,800 garages', 'Instant policy PDF'].map((f) => (
                  <span key={f} className="plan-card-chip">{f}</span>
                ))}
              </div>
            )}
          </button>
        )
      })}
    </div>
  )
}

// ── Rich card: summary ────────────────────────────────────────────────
function SummaryCard({ lines = [], total = '₹11,980', onPay }) {
  const defaultLines = lines.length ? lines : [
    { label: 'Own damage', value: '₹8,640' },
    { label: '3rd party', value: '₹1,740' },
    { label: 'Zero dep add-on', value: '₹980' },
    { label: 'GST (18%)', value: '₹2,430' },
  ]
  return (
    <div className="summary-card">
      <div className="summary-card-title">Quote summary</div>
      {defaultLines.map((l) => (
        <div key={l.label} className="summary-line">
          <span className="summary-line-label">{l.label}</span>
          <span className="summary-line-value">{l.value}</span>
        </div>
      ))}
      <hr className="summary-divider" />
      <div className="summary-total">
        <span className="summary-total-label">Total (incl. GST)</span>
        <span className="summary-total-amount">{total}</span>
      </div>
      <button className="summary-cta" onClick={onPay}>Pay &amp; get policy →</button>
    </div>
  )
}

// ── Base message components ───────────────────────────────────────────
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
      {success && (
        <svg width="10" height="10" viewBox="0 0 10 10">
          <path d="M2 5l2 2 4-4" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" />
        </svg>
      )}
      <span>{text}</span>
    </div>
  )
}

function BotMessage({ content }) {
  return (
    <div className="message bot">
      <div className="message-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    </div>
  )
}

function UserMessage({ content }) {
  return (
    <div className="message user">
      <div className="message-content">{content}</div>
    </div>
  )
}

function AttachmentMessage({ name }) {
  return (
    <div className="message user">
      <div className="message-content attachment">
        <div className="attachment-name">{name}</div>
        <div className="attachment-hint">Uploaded</div>
      </div>
    </div>
  )
}

// ── Welcome screen ────────────────────────────────────────────────────
function Welcome({ onStart, onUpload, user }) {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const id = setTimeout(() => setReady(true), 80)
    return () => clearTimeout(id)
  }, [])

  const firstName = user?.name?.split(' ')[0] || null

  return (
    <div className={`welcome${ready ? ' welcome-ready' : ''}`}>
      <div className="welcome-car"><CarSilhouette /></div>

      <div className="welcome-eyebrow">▲ Chatty · est. 2026</div>

      <h1 className="welcome-headline">
        <span className="hl-line hl-line-1">
          {firstName ? `Welcome back, ${firstName}.` : 'Good evening.'}
        </span>
        <span className="hl-line hl-line-2">Let's get your car</span>
        <span className="hl-line hl-line-3">
          covered <em>— properly.</em>
        </span>
      </h1>

      <p className="welcome-sub">
        Tell us your registration number, snap a photo of your RC, or just say hi. We'll handle the paperwork.
      </p>

      <div className="welcome-actions">
        <button className="cta-primary" onClick={() => onStart()}>
          <span>Finish in 60 seconds</span>
          <span className="cta-arrow">
            <svg width="14" height="14" viewBox="0 0 14 14">
              <path d="M2 7h10m-4-4l4 4-4 4" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </button>
        <div className="cta-row">
          <button className="cta-soft" onClick={onUpload}>
            <svg width="14" height="14" viewBox="0 0 14 14">
              <path d="M10 5v-.5a3 3 0 0 0-6 0V5M3.5 6h7v6h-7z" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Upload RC
          </button>
          <button className="cta-soft" onClick={() => onStart('voice')}>
            <svg width="14" height="14" viewBox="0 0 14 14">
              <rect x="5" y="1.5" width="4" height="7" rx="2" stroke="currentColor" strokeWidth="1.3" fill="none" />
              <path d="M3 7a4 4 0 0 0 8 0M7 11v1.5" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinecap="round" />
            </svg>
            Talk to us
          </button>
        </div>
        <div className="trust-strip">
          <span>IRDAI regulated</span>
          <span className="trust-dot" />
          <span>4.9 · 128k reviews</span>
          <span className="trust-dot" />
          <span>Claims 94%</span>
        </div>
      </div>
    </div>
  )
}

function getSpeechLang(language) {
  return language === 'hindi' ? 'hi-IN' : 'en-IN'
}

export default function Chat({ onOpenAdmin, user, googleClientId, onSignIn, onSignOut }) {
  const [messages, setMessages] = useState([])
  const [progressEvents, setProgressEvents] = useState([])
  const [streamingText, setStreamingText] = useState('')
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  const [ux, setUx] = useState(null)
  const [multiSelection, setMultiSelection] = useState([])
  const [started, setStarted] = useState(false)
  const [runtimeConfig, setRuntimeConfig] = useState(null)
  const [voicePrefs, setVoicePrefs] = useState({
    outputEnabled: false,
    inputEnabled: false,
    language: 'english',
    tone: 'friendly',
    detailLevel: 'quick',
    autoPlay: false,
    interruptible: true,
    speed: 'normal',
    ttsVoice: 'alloy',
  })
  const [voiceStatus, setVoiceStatus] = useState('')
  const [listening, setListening] = useState(false)
  const [speechSupported, setSpeechSupported] = useState(false)

  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)
  const sessionIdRef = useRef(null)
  const lastBotMessageRef = useRef('')
  const uxRef = useRef(null)
  const recognitionRef = useRef(null)
  const spokenTextRef = useRef('')
  const currentAudioRef = useRef(null)

  const outputAvailable = runtimeConfig?.voice?.output_enabled ?? false
  const inputAvailable = runtimeConfig?.voice?.input_enabled ?? false

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  useEffect(() => {
    let cancelled = false
    getPublicRuntimeConfig()
      .then((cfg) => {
        if (cancelled) return
        setRuntimeConfig(cfg)
        setVoicePrefs({
          outputEnabled: Boolean(cfg.voice?.output_enabled),
          inputEnabled: Boolean(cfg.voice?.input_enabled),
          language: cfg.voice?.language || 'english',
          tone: cfg.voice?.tone || 'friendly',
          detailLevel: cfg.voice?.detail_level || 'quick',
          autoPlay: Boolean(cfg.voice?.auto_play),
          interruptible: cfg.voice?.interruptible !== false,
          speed: cfg.voice?.speed || 'normal',
          ttsVoice: cfg.voice?.tts_voice || 'alloy',
        })
      })
      .catch(() => {})

    const supported =
      typeof window !== 'undefined' &&
      (window.SpeechRecognition || window.webkitSpeechRecognition || window.speechSynthesis)
    setSpeechSupported(Boolean(supported))

    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.getVoices()
    }

    return () => {
      cancelled = true
      if (currentAudioRef.current) {
        currentAudioRef.current.pause()
        currentAudioRef.current = null
      }
      if (typeof window !== 'undefined' && window.speechSynthesis) {
        window.speechSynthesis.cancel()
      }
      if (recognitionRef.current) {
        recognitionRef.current.abort()
      }
    }
  }, [])

  const stopSpeaking = useCallback(() => {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause()
      currentAudioRef.current.src = ''
      currentAudioRef.current = null
    }
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }
    spokenTextRef.current = ''
  }, [])

  const pickVoice = useCallback((lang) => {
    if (typeof window === 'undefined' || !window.speechSynthesis) return null
    const voices = window.speechSynthesis.getVoices()
    if (!voices.length) return null
    const preferredLang = getSpeechLang(lang)
    return (
      voices.find((voice) => voice.lang === preferredLang && /india|indian/i.test(voice.name)) ||
      voices.find((voice) => voice.lang === preferredLang) ||
      voices.find((voice) => voice.lang.startsWith(preferredLang.slice(0, 2)) && /india|indian/i.test(voice.name)) ||
      voices.find((voice) => voice.lang.startsWith(preferredLang.slice(0, 2))) ||
      null
    )
  }, [])

  const speakText = useCallback(async (text) => {
    if (!voicePrefs.outputEnabled || !text) return
    if (voicePrefs.interruptible) stopSpeaking()
    else if (currentAudioRef.current && !currentAudioRef.current.ended) return

    spokenTextRef.current = text
    setVoiceStatus('Speaking...')

    try {
      const speedMap = { slow: 0.75, normal: 1.0, fast: 1.25 }
      const res = await fetch('/api/voice/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text,
          voice: voicePrefs.ttsVoice || 'alloy',
          speed: speedMap[voicePrefs.speed] || 1.0,
          language: voicePrefs.language,
        }),
      })
      if (res.ok) {
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const audio = new Audio(url)
        currentAudioRef.current = audio
        audio.play()
        audio.onended = () => {
          URL.revokeObjectURL(url)
          currentAudioRef.current = null
          if (spokenTextRef.current === text) setVoiceStatus('')
          spokenTextRef.current = ''
        }
        audio.onerror = () => {
          URL.revokeObjectURL(url)
          currentAudioRef.current = null
          if (spokenTextRef.current === text) setVoiceStatus('')
          spokenTextRef.current = ''
        }
        return
      }
    } catch {
      // Fall through to browser TTS
    }

    if (typeof window === 'undefined' || !window.speechSynthesis) {
      setVoiceStatus('')
      spokenTextRef.current = ''
      return
    }
    const synth = window.speechSynthesis
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = getSpeechLang(voicePrefs.language)
    utterance.rate = SPEED_RATES[voicePrefs.speed] || 1
    const selectedVoice = pickVoice(voicePrefs.language)
    if (selectedVoice) utterance.voice = selectedVoice
    utterance.onend = () => {
      if (spokenTextRef.current === text) setVoiceStatus('')
      spokenTextRef.current = ''
    }
    utterance.onerror = () => {
      if (spokenTextRef.current === text) setVoiceStatus('')
      spokenTextRef.current = ''
    }
    synth.speak(utterance)
  }, [pickVoice, stopSpeaking, voicePrefs])

  const requestVoiceGuide = useCallback(async ({
    message, nextUx, stage, query, forcePlay = false,
  }) => {
    if (!message || !outputAvailable) return null
    if (!voicePrefs.autoPlay && !forcePlay) return null

    setVoiceStatus('Preparing voice...')
    if (voicePrefs.interruptible) stopSpeaking()

    const speedMap = { slow: 0.75, normal: 1.0, fast: 1.25 }
    const body = JSON.stringify({
      message, ux: nextUx, stage, query,
      language: voicePrefs.language,
      detail_level: voicePrefs.detailLevel,
      tone: voicePrefs.tone,
      voice: voicePrefs.ttsVoice || 'alloy',
      speed: speedMap[voicePrefs.speed] || 1.0,
    })

    try {
      const res = await fetch('/api/voice/speak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      })
      if (!res.ok) throw new Error(`${res.status}`)

      const spokenText = decodeURIComponent(res.headers.get('X-Voice-Text') || '')
      spokenTextRef.current = spokenText
      setVoiceStatus('Speaking...')

      const mimeType = 'audio/mpeg'
      if (
        typeof MediaSource !== 'undefined' &&
        MediaSource.isTypeSupported?.(mimeType) &&
        res.body
      ) {
        const [stream1, stream2] = res.body.tee()
        try {
          await _playStreamingAudio(stream1, mimeType)
          stream2.cancel()
          return spokenText
        } catch {
          const blob = await new Response(stream2).blob()
          const url = URL.createObjectURL(blob)
          const audio = new Audio(url)
          currentAudioRef.current = audio
          audio.play()
          audio.onended = () => {
            URL.revokeObjectURL(url)
            currentAudioRef.current = null
            setVoiceStatus('')
            spokenTextRef.current = ''
          }
          return spokenText
        }
      }

      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      currentAudioRef.current = audio
      audio.play()
      audio.onended = () => {
        URL.revokeObjectURL(url)
        currentAudioRef.current = null
        setVoiceStatus('')
        spokenTextRef.current = ''
      }
      return spokenText
    } catch (err) {
      setVoiceStatus(`Voice unavailable: ${err.message}`)
      return null
    }

    async function _playStreamingAudio(body, mimeType) {
      return new Promise((resolve, reject) => {
        const ms = new MediaSource()
        const audio = new Audio()
        const msUrl = URL.createObjectURL(ms)
        audio.src = msUrl
        currentAudioRef.current = audio

        ms.addEventListener('sourceopen', async () => {
          let sb
          try { sb = ms.addSourceBuffer(mimeType) }
          catch (e) { reject(e); return }

          const reader = body.getReader()
          let started = false

          const pump = async () => {
            const { done, value } = await reader.read()
            if (done) {
              if (!sb.updating) { try { ms.endOfStream() } catch {} }
              else sb.addEventListener('updateend', () => { try { ms.endOfStream() } catch {} }, { once: true })
              resolve()
              return
            }
            const append = () => {
              try { sb.appendBuffer(value) } catch (e) { reject(e); return }
              if (!started) { started = true; audio.play().catch(() => {}) }
            }
            if (sb.updating) sb.addEventListener('updateend', () => { append(); pump() }, { once: true })
            else { append(); pump() }
          }
          pump()
        }, { once: true })

        audio.onended = () => {
          URL.revokeObjectURL(msUrl)
          currentAudioRef.current = null
          setVoiceStatus('')
          spokenTextRef.current = ''
        }
        audio.onerror = reject
      })
    }
  }, [outputAvailable, stopSpeaking, voicePrefs])

  const handleEvent = useCallback((evt) => {
    if (evt.type === 'session') {
      setSessionId(evt.session_id)
      sessionIdRef.current = evt.session_id
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
      const nextUx = evt.ux || null
      setProgressEvents([])
      setStreamingText('')
      setMessages((m) => [...m, {
        role: 'bot',
        content: evt.text,
        uxKind: nextUx?.kind,
        uxData: nextUx,
      }])
      setUx(nextUx)
      uxRef.current = nextUx
      lastBotMessageRef.current = evt.text
      if (voicePrefs.outputEnabled && voicePrefs.autoPlay && outputAvailable) {
        void requestVoiceGuide({
          message: evt.text,
          nextUx,
          stage: nextUx?.stage || null,
        })
      } else {
        setVoiceStatus('')
      }
    } else if (evt.type === 'error') {
      setProgressEvents([])
      setStreamingText('')
      setMessages((m) => [
        ...m,
        { role: 'bot', content: `Sorry, something went wrong: ${evt.text}` },
      ])
    }
  }, [outputAvailable, requestVoiceGuide, voicePrefs.autoPlay, voicePrefs.outputEnabled])

  const send = useCallback(async (text) => {
    const msg = (text || '').trim()
    if (!msg || loading) return
    setStarted(true)
    setInput('')
    setUx(null)
    uxRef.current = null
    setMultiSelection([])
    setMessages((m) => [...m, { role: 'user', content: msg }])
    setProgressEvents([])
    setStreamingText('')
    setLoading(true)
    if (voicePrefs.interruptible) stopSpeaking()
    setVoiceStatus('')

    if (textareaRef.current) textareaRef.current.style.height = '44px'

    try {
      await streamChat({ message: msg, sessionId, onEvent: handleEvent })
    } catch (err) {
      setMessages((m) => [...m, { role: 'bot', content: `Network error: ${err.message}` }])
    } finally {
      setLoading(false)
    }
  }, [handleEvent, loading, sessionId, stopSpeaking, voicePrefs.interruptible])

  const triggerFilePicker = () => {
    if (loading) return
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e) => {
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    if (!files.length) return
    if (voicePrefs.interruptible) stopSpeaking()

    for (const file of files) {
      if (file.size > 10 * 1024 * 1024) {
        setMessages((m) => [
          ...m,
          { role: 'bot', content: `${file.name} is larger than 10 MB. Please compress or try a different one.` },
        ])
        continue
      }

      setStarted(true)
      setUx(null)
      uxRef.current = null
      setMultiSelection([])
      setMessages((m) => [...m, { role: 'attachment', content: file.name }])
      setProgressEvents([])
      setStreamingText('')
      setLoading(true)
      setVoiceStatus('')

      try {
        await uploadDocument({ file, sessionId: sessionIdRef.current, onEvent: handleEvent })
      } catch (err) {
        setMessages((m) => [
          ...m,
          { role: 'bot', content: `Couldn't upload ${file.name}: ${err.message}` },
        ])
      } finally {
        setLoading(false)
      }
    }
  }

  const handleReset = async () => {
    if (voicePrefs.interruptible) stopSpeaking()
    if (recognitionRef.current) recognitionRef.current.abort()
    await resetSession(sessionId)
    setMessages([])
    setSessionId(null)
    sessionIdRef.current = null
    setStarted(false)
    setInput('')
    setUx(null)
    uxRef.current = null
    lastBotMessageRef.current = ''
    setProgressEvents([])
    setStreamingText('')
    setMultiSelection([])
    setVoiceStatus('')
    setListening(false)
  }

  const handleChoiceClick = (opt) => send(opt.label)

  const handleMultiToggle = (opt) => {
    setMultiSelection((cur) => {
      const exists = cur.find((x) => x.value === opt.value)
      return exists ? cur.filter((x) => x.value !== opt.value) : [...cur, opt]
    })
  }

  const handleMultiApply = () => {
    if (!multiSelection.length) { send('Skip add-ons for now'); return }
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

  const isUploadSuggestion = (label) =>
    typeof label === 'string' && /upload|rc card|policy.*pdf|document/i.test(label)

  const handleSuggestion = (label) => {
    if (isUploadSuggestion(label)) triggerFilePicker()
    else send(label)
  }

  const processVoiceTranscript = useCallback(async (transcript) => {
    setVoiceStatus(`Heard: ${transcript}`)
    try {
      const result = await classifyVoiceIntent({
        transcript,
        message: lastBotMessageRef.current,
        ux: uxRef.current,
        stage: uxRef.current?.stage || null,
      })

      if (result.intent === 'clarification') {
        await requestVoiceGuide({
          message: lastBotMessageRef.current,
          nextUx: uxRef.current,
          stage: uxRef.current?.stage || null,
          query: transcript,
          forcePlay: true,
        })
        return
      }

      if (result.intent === 'ambiguous') {
        const followUp = result.follow_up || 'Do you want me to explain this screen or send that as your reply?'
        setVoiceStatus(followUp)
        if (voicePrefs.outputEnabled && outputAvailable) speakText(followUp)
        return
      }

      setVoiceStatus(result.intent === 'detailed_question' ? 'Sending your question to chat...' : 'Using that as your reply...')
      await send(transcript)
    } catch (err) {
      setVoiceStatus(`Voice input failed: ${err.message}`)
    }
  }, [outputAvailable, requestVoiceGuide, send, speakText, voicePrefs.outputEnabled])

  const toggleListening = () => {
    if (!inputAvailable) return
    if (!speechSupported || typeof window === 'undefined') {
      setVoiceStatus('Speech input is not supported in this browser.')
      return
    }
    if (loading) return

    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!Recognition) {
      setVoiceStatus('Speech recognition is not supported in this browser.')
      return
    }

    if (listening && recognitionRef.current) {
      recognitionRef.current.stop()
      return
    }

    const recognition = new Recognition()
    recognitionRef.current = recognition
    recognition.lang = getSpeechLang(voicePrefs.language)
    recognition.interimResults = true
    recognition.continuous = false
    let finalTranscript = ''

    recognition.onstart = () => {
      setListening(true)
      setVoiceStatus('Listening...')
      if (voicePrefs.interruptible) stopSpeaking()
    }

    recognition.onresult = (event) => {
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const transcript = event.results[i][0]?.transcript || ''
        if (event.results[i].isFinal) finalTranscript += `${transcript} `
        else interim += transcript
      }
      const preview = `${finalTranscript} ${interim}`.trim()
      setVoiceStatus(preview || 'Listening...')
    }

    recognition.onerror = (event) => {
      if (event.error !== 'no-speech') {
        setVoiceStatus(`Voice input error: ${event.error}`)
      }
    }

    recognition.onend = () => {
      recognitionRef.current = null
      setListening(false)
      const spoken = finalTranscript.trim()
      if (spoken) void processVoiceTranscript(spoken)
      else if (!loading) setVoiceStatus('')
    }

    recognition.start()
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
              <button
                key={s}
                className={`chip${isUploadSuggestion(s) ? ' upload-chip' : ''}`}
                onClick={() => handleSuggestion(s)}
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>
    )
  }

  const renderMessage = (m, i) => {
    if (m.role === 'attachment') return <AttachmentMessage key={i} name={m.content} />
    if (m.role === 'user') return <UserMessage key={i} content={m.content} />
    // Bot messages — check for rich card variants
    if (m.uxKind === 'vehicle_found') {
      const v = m.uxData?.vehicle || m.uxData || {}
      return <CarFoundCard
        key={i}
        reg={v.registration || v.reg || 'XXXXXXX'}
        make={v.make || 'Vehicle'}
        model={v.model || ''}
        year={v.year || ''}
      />
    }
    if (m.uxKind === 'plan_selection') {
      return <PlanCards key={i} onSelect={(p) => send(`I'll go with the ${p.name} plan`)} />
    }
    if (m.uxKind === 'summary') {
      return <SummaryCard key={i} onPay={() => send('Proceed to pay')} />
    }
    return <BotMessage key={i} content={m.content} />
  }

  return (
    <>
      {/* ── Header ── */}
      <div className="header">
        <div className="header-brand">
          <Logomark />
          <span className="header-brand-name">Chatty</span>
        </div>
        <div className="header-actions">
          {outputAvailable && (
            <button
              className={`header-btn voice-toggle${voicePrefs.outputEnabled ? ' active' : ''}`}
              onClick={() => {
                if (!outputAvailable) return
                setVoicePrefs((state) => ({ ...state, outputEnabled: !state.outputEnabled }))
                if (voicePrefs.outputEnabled) stopSpeaking()
              }}
              title="Toggle voice output"
            >
              {voicePrefs.outputEnabled ? '🔊' : '🔈'}
            </button>
          )}
          {(outputAvailable || inputAvailable) && (
            <select
              className="voice-select"
              value={voicePrefs.language}
              onChange={(e) => setVoicePrefs((state) => ({ ...state, language: e.target.value }))}
            >
              <option value="english">EN</option>
              <option value="hindi">HI</option>
            </select>
          )}
          {inputAvailable && (
            <button
              className={`header-btn voice-toggle${listening ? ' listening' : ''}`}
              onClick={toggleListening}
              title="Talk to the assistant"
            >
              {listening ? '🎙️' : '🎤'}
            </button>
          )}
          {started && (
            <button className="header-btn" onClick={handleReset} title="New chat">
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                <g stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
                  <path d="M13 3v3.5h-3.5" />
                  <path d="M12.7 7A5 5 0 1 0 8 13" />
                </g>
              </svg>
              New
            </button>
          )}
          <button className="header-btn" onClick={onOpenAdmin} title="Admin">
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.4" />
              <path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3.2 3.2l1.1 1.1M11.7 11.7l1.1 1.1M3.2 12.8l1.1-1.1M11.7 4.3l1.1-1.1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
          </button>
          <GoogleSignIn
            user={user}
            googleClientId={googleClientId}
            onSignIn={onSignIn}
            onSignOut={onSignOut}
          />
        </div>
      </div>

      {/* ── Banner ── */}
      <div className="banner">
        <strong>Monsoon sale</strong>
        <span>· up to 20% off select plans</span>
      </div>

      {/* ── Voice status ── */}
      {voiceStatus && (
        <div className="voice-status">
          <span>{listening ? '🎙️' : '🔊'}</span>
          <span>{voiceStatus}</span>
        </div>
      )}

      {/* ── Main content ── */}
      {!started ? (
        <Welcome
          user={user}
          onStart={(mode) => {
            send("Hi, I'd like to get car insurance")
            if (mode === 'voice' && inputAvailable) setTimeout(toggleListening, 400)
          }}
          onUpload={triggerFilePicker}
        />
      ) : (
        <div className="messages">
          {messages.map(renderMessage)}
          {progressEvents.map((p) => (
            <ProgressPill key={p.id} text={p.text} success={p.done} />
          ))}
          {streamingText && <BotMessage content={streamingText} />}
          {loading && progressEvents.length === 0 && !streamingText && <TypingDots />}
          <div ref={messagesEndRef} />
        </div>
      )}

      {started && renderInteractive()}

      {/* ── Input dock ── */}
      {started && <div className="input-area">
        <div className="input-row">
          <button
            className="attach-btn"
            onClick={triggerFilePicker}
            disabled={loading}
            aria-label="Attach file"
            title="Upload RC card or policy"
          >
            <svg width="18" height="18" viewBox="0 0 18 18">
              <path d="M11.5 4.5L5 11a2.5 2.5 0 0 0 3.5 3.5L14 9a4 4 0 0 0-5.5-5.5L3 9"
                stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          {inputAvailable && (
            <button
              className={`attach-btn mic-btn${listening ? ' active' : ''}`}
              onClick={toggleListening}
              disabled={loading}
              aria-label="Speak"
              title="Speak"
            >
              <svg width="18" height="18" viewBox="0 0 18 18">
                <rect x="6.5" y="2" width="5" height="9" rx="2.5" stroke="currentColor" strokeWidth="1.4" fill="none" />
                <path d="M3.5 9a5.5 5.5 0 0 0 11 0M9 14.5V16" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" />
              </svg>
            </button>
          )}
          <div className="input-wrapper">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              placeholder={started ? 'Ask anything about your coverage...' : 'Enter your registration number...'}
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
            <svg width="14" height="14" viewBox="0 0 14 14">
              <path d="M2 7h10m-4-4l4 4-4 4" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>}

      {/* Always in DOM so triggerFilePicker works from the welcome screen too */}
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_UPLOAD_TYPES}
        multiple
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />
    </>
  )
}
