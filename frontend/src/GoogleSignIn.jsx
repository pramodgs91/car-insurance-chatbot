import { useEffect, useRef, useState } from 'react'

function initials(name, email) {
  if (name && name.trim()) {
    const parts = name.trim().split(' ')
    return (parts[0][0] + (parts[1]?.[0] || '')).toUpperCase()
  }
  return (email?.[0] || '?').toUpperCase()
}

export default function GoogleSignIn({ user, googleClientId, onSignIn, onSignOut }) {
  const btnRef = useRef(null)
  const [showMenu, setShowMenu] = useState(false)

  useEffect(() => {
    if (!googleClientId || user) return

    const setup = () => {
      if (!window.google?.accounts?.id) return
      window.google.accounts.id.initialize({
        client_id: googleClientId,
        callback: (resp) => onSignIn(resp.credential),
        auto_select: false,
      })
      if (btnRef.current) {
        window.google.accounts.id.renderButton(btnRef.current, {
          theme: 'filled_black',
          size: 'medium',
          shape: 'pill',
          text: 'signin',
          logo_alignment: 'left',
        })
      }
    }

    if (window.google?.accounts?.id) {
      setup()
    } else {
      // Dynamically load the GIS script
      if (!document.querySelector('script[src*="accounts.google.com/gsi"]')) {
        const s = document.createElement('script')
        s.src = 'https://accounts.google.com/gsi/client'
        s.async = true
        s.onload = setup
        document.head.appendChild(s)
      } else {
        // Script already injected but not loaded yet — wait
        const interval = setInterval(() => {
          if (window.google?.accounts?.id) {
            clearInterval(interval)
            setup()
          }
        }, 100)
        return () => clearInterval(interval)
      }
    }
  }, [googleClientId, user, onSignIn])

  // Close dropdown on outside click
  useEffect(() => {
    if (!showMenu) return
    const close = () => setShowMenu(false)
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [showMenu])

  if (!googleClientId) return null

  if (user) {
    return (
      <div className="user-badge-wrap">
        <button
          className="user-badge"
          onClick={(e) => { e.stopPropagation(); setShowMenu((v) => !v) }}
          title={user.email}
        >
          {initials(user.name, user.email)}
        </button>
        {showMenu && (
          <div className="user-menu">
            <div className="user-menu-info">
              <div className="user-menu-name">{user.name || user.email}</div>
              <div className="user-menu-email">{user.email}</div>
            </div>
            <button className="user-menu-signout" onClick={onSignOut}>Sign out</button>
          </div>
        )}
      </div>
    )
  }

  return <div ref={btnRef} className="google-signin-btn" />
}
