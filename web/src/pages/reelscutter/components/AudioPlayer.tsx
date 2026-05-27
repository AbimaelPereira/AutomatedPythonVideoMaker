import { Play, Pause } from 'lucide-react'

interface Props {
  currentTime: number
  duration: number
  playing: boolean
  // se definido, o player exibe e opera dentro desse range
  range?: { start: number; end: number }
  // quando currentTime está fora do range, desabilita visualmente
  dimWhenOutOfRange?: boolean
  label?: string
  onPlayPause: () => void
  onSeek: (t: number) => void
  className?: string
}

function fmt(s: number) {
  if (!isFinite(s) || s < 0) s = 0
  const m = Math.floor(s / 60)
  const ss = Math.floor(s % 60)
  return `${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

export default function AudioPlayer({
  currentTime,
  duration,
  playing,
  range,
  dimWhenOutOfRange = false,
  label,
  onPlayPause,
  onSeek,
  className = '',
}: Props) {
  const total    = range ? range.end - range.start : duration
  const relative = range ? Math.max(0, currentTime - range.start) : currentTime
  const pct      = total > 0 ? Math.min(100, (relative / total) * 100) : 0

  const outOfRange = dimWhenOutOfRange && range
    && (currentTime < range.start || currentTime >= range.end)

  function handleBarClick(e: React.MouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect()
    const frac = (e.clientX - rect.left) / rect.width
    const target = range
      ? range.start + frac * (range.end - range.start)
      : frac * duration
    onSeek(Math.max(0, Math.min(duration, target)))
  }

  return (
    <div className={`flex items-center gap-3 ${outOfRange ? 'opacity-40' : ''} ${className}`}>
      {/* Play/Pause */}
      <button
        onClick={onPlayPause}
        disabled={!!outOfRange}
        className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-colors bg-navy-700 hover:bg-navy-600 text-white disabled:cursor-not-allowed"
      >
        {playing && !outOfRange ? <Pause size={14} /> : <Play size={14} />}
      </button>

      {/* Barra */}
      <div className="flex-1 flex flex-col gap-1">
        {label && <span className="text-[10px] text-navy-500 leading-none">{label}</span>}
        <div
          className="relative h-1.5 rounded-full cursor-pointer group"
          style={{ background: '#1e3470' }}
          onClick={handleBarClick}
        >
          {/* range highlight */}
          {range && duration > 0 && (
            <div
              className="absolute inset-y-0 rounded-full"
              style={{
                left:  `${(range.start / duration) * 100}%`,
                width: `${((range.end - range.start) / duration) * 100}%`,
                background: '#2f4a8f',
              }}
            />
          )}
          {/* progresso */}
          <div
            className="absolute inset-y-0 left-0 rounded-full transition-none"
            style={{
              width: `${range
                ? (range.start / duration) * 100 + pct * ((range.end - range.start) / duration)
                : pct}%`,
              background: outOfRange ? '#3d5ca8' : '#5a76b5',
            }}
          />
          {/* thumb */}
          <div
            className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white shadow opacity-0 group-hover:opacity-100 transition-opacity"
            style={{
              left: `calc(${range
                ? (range.start / duration) * 100 + pct * ((range.end - range.start) / duration)
                : pct}% - 6px)`,
            }}
          />
        </div>

        {/* Tempos */}
        <div className="flex justify-between text-[10px] text-navy-600 font-mono">
          <span>{fmt(range ? currentTime : currentTime)}</span>
          <span>{fmt(range ? range.end : duration)}</span>
        </div>
      </div>
    </div>
  )
}
