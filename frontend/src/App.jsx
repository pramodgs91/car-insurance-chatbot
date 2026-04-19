import { useState, useEffect } from 'react'
import Chat from './Chat'
import Admin from './Admin'
import { getAuthConfig, verifyGoogleCredential, userLogout } from './api'

// Detect ?admin=1 in the URL — used when admin opens in a new tab
const IS_ADMIN_TAB = new URLSearchParams(window.location.search).has('admin')

export default function App() {
  const [user, setUser] = useState(null)           // { email, name, token }
  const [googleClientId, setGoogleClientId] = useState(null)
  const [authReady, setAuthReady] = useState(false)

  // Load auth config + restore saved session
  useEffect(() => {
    const savedToken = localStorage.getItem('user_token')
    const savedEmail = localStorage.getItem('user_email')
    const savedName  = localStorage.getItem('user_name')
    if (savedToken && savedEmail) {
      setUser({ token: savedToken, email: savedEmail, name: savedName || '' })
    }

    getAuthConfig()
      .then((cfg) => {
        if (cfg.google_configured) setGoogleClientId(cfg.google_client_id)
      })
      .catch(() => {})
      .finally(() => setAuthReady(true))
  }, [])

  const handleSignIn = async (credential) => {
    try {
      const info = await verifyGoogleCredential(credential)
      localStorage.setItem('user_token', info.token)
      localStorage.setItem('user_email', info.email)
      localStorage.setItem('user_name', info.name)
      setUser({ token: info.token, email: info.email, name: info.name })
    } catch (err) {
      console.error('Sign-in failed:', err)
    }
  }

  const handleSignOut = async () => {
    await userLogout()
    localStorage.removeItem('user_token')
    localStorage.removeItem('user_email')
    localStorage.removeItem('user_name')
    setUser(null)
  }

  const openAdmin = () => {
    window.open(`${window.location.pathname}?admin=1`, '_blank')
  }

  if (IS_ADMIN_TAB) {
    return (
      <div className="app">
        <Admin onClose={() => window.close()} standalone />
      </div>
    )
  }

  return (
    <div className="app">
      <Chat
        user={user}
        googleClientId={authReady ? googleClientId : undefined}
        onSignIn={handleSignIn}
        onSignOut={handleSignOut}
        onOpenAdmin={openAdmin}
      />
    </div>
  )
}
