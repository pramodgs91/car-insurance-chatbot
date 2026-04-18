import { useState } from 'react'
import Chat from './Chat'
import Admin from './Admin'

export default function App() {
  const [showAdmin, setShowAdmin] = useState(false)
  return (
    <div className="app">
      <Chat onOpenAdmin={() => setShowAdmin(true)} />
      {showAdmin && <Admin onClose={() => setShowAdmin(false)} />}
    </div>
  )
}
