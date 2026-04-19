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

const INITIAL_SUGGESTIONS = [
  'I want to buy car insurance',
  'My reg is KA05NG2604',
  'Help me renew',
  'What is Zero Depreciation?',
  'Third-party vs Comprehensive',
]

const ACCEPTED_UPLOAD_TYPES = '.pdf,.jpg,.jpeg,.png,.webp,image/*,application/pdf'
const SPEED_RATES = { slow: 0.9, normal: 1, fast: 1.12 }

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

function getSpeechLang(language) {
  return language === 'hindi' ? 'hi-IN' : 'en-IN'
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

    // Try backend TTS (gpt-4o-mini-tts) first
    try {
      const speedMap = { slow: 0.75, normal: 1.0, fast: 1.25 }
      const res = await fetch('/api/voice/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text,
          voice: voicePrefs.ttsVoice || 'alloy',
          speed: speedMap[voicePrefs.speed] || 1.0,
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

    // Browser TTS fallback
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
    message,
    nextUx,
    stage,
    query,
    forcePlay = false,
  }) => {
    if (!message || !outputAvailable) return null
    setVoiceStatus(query ? 'Explaining the current screen...' : 'Preparing voice guide...')
    try {
      const response = await getVoiceGuide({
        message,
        ux: nextUx,
        stage,
        query,
        language: voicePrefs.language,
        detail_level: voicePrefs.detailLevel,
        tone: voicePrefs.tone,
      })
      const spoken = response.text || ''
      if ((voicePrefs.autoPlay || forcePlay) && voicePrefs.outputEnabled) {
        speakText(spoken)
      } else {
        setVoiceStatus(spoken ? `Voice ready: ${spoken}` : '')
      }
      return spoken
    } catch (err) {
      setVoiceStatus(`Voice unavailable: ${err.message}`)
      return null
    }
  }, [outputAvailable, speakText, voicePrefs])

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
      setMessages((m) => [...m, { role: 'bot', content: evt.text }])
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
      if (spoken) {
        void processVoiceTranscript(spoken)
      } else if (!loading) {
        setVoiceStatus('')
      }
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
              <option value="english">English</option>
              <option value="hindi">Hindi</option>
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
            <button className="header-btn" onClick={handleReset}>New chat</button>
          )}
          <button className="header-btn" onClick={onOpenAdmin}>Admin</button>
        </div>
      </div>

      <div className="banner">
        <span>🎉</span>
        <span><strong>Season Sale:</strong> Up to 20% off on select plans</span>
      </div>

      {voiceStatus && (
        <div className="voice-status">
          <span>{listening ? '🎙️' : '🔊'}</span>
          <span>{voiceStatus}</span>
        </div>
      )}

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
          {inputAvailable && (
            <button
              className={`attach-btn mic-btn${listening ? ' active' : ''}`}
              onClick={toggleListening}
              disabled={loading}
              aria-label="Speak"
              title="Speak"
            >
              {listening ? '🎙️' : '🎤'}
            </button>
          )}
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
          multiple
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
      </div>
    </>
  )
}
