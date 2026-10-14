import { useEffect, useState } from 'react'

type Health = { status: string; version: string }

function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetch('/api/health')
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then(setHealth)
      .catch(() => setError(true))
  }, [])

  return (
    <main>
      <h1>failsight</h1>
      <p>See why your agents fail — and stop them from failing.</p>
      <p className="status">
        {health && `Server ${health.status} · v${health.version}`}
        {error && 'Server unreachable'}
        {!health && !error && 'Connecting…'}
      </p>
    </main>
  )
}

export default App
