import { useEffect, useState } from 'react'

const UNITS = ['Days', 'Hrs', 'Min', 'Sec'] as const

function parts(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000))
  return [Math.floor(s / 86400), Math.floor((s % 86400) / 3600), Math.floor((s % 3600) / 60), s % 60]
}

// A stadium-scoreboard countdown. Each digit flips when it changes.
export default function Countdown({ to }: { to: Date }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  const values = parts(to.getTime() - now)
  const [d, h, m] = values

  return (
    <div className="scoreboard" role="timer" aria-label={`${d} days, ${h} hours, ${m} minutes until kickoff`}>
      {values.map((v, i) => (
        <div className="score-cell" key={UNITS[i]}>
          <div className="score-digits" aria-hidden="true">
            {String(Math.min(v, 99)).padStart(2, '0').split('').map((ch, j) => (
              // the key includes the digit, so React re-mounts it and the flip animation replays
              <span className="score-digit" key={`${j}-${ch}`}>{ch}</span>
            ))}
          </div>
          <span className="score-unit">{UNITS[i]}</span>
        </div>
      ))}
    </div>
  )
}
