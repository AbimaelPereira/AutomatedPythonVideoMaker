import { useId } from 'react'

interface Props {
  label: string
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  step?: number
  /** Sufixo mostrado ao lado do valor (ex.: "px", "%"). */
  unit?: string
  /** Casas decimais na exibição. Default: deduzido do `step`. */
  decimals?: number
  disabled?: boolean
}

/**
 * Slider com o valor sempre visível e editável por digitação.
 *
 * O campo numérico ao lado não é decoração: arrastar é bom para explorar, mas
 * ruim para repetir um valor exato entre thumbnails. Os dois editam o mesmo
 * estado.
 */
export default function Slider({
  label, value, onChange, min = 0, max = 100, step = 1,
  unit = '', decimals, disabled = false,
}: Props) {
  const id = useId()

  // Sem `decimals` explícito, deduz do step: 0.05 → 2 casas, 1 → nenhuma.
  const places = decimals ?? (String(step).split('.')[1]?.length ?? 0)

  // Posição do preenchimento colorido à esquerda do polegar.
  const pct = max > min ? ((value - min) / (max - min)) * 100 : 0

  const clamp = (v: number) => Math.min(max, Math.max(min, v))

  return (
    <div className={disabled ? 'opacity-50 pointer-events-none' : ''}>
      <div className="flex items-baseline justify-between mb-1.5 gap-2">
        <label htmlFor={id} className="text-xs font-medium text-navy-300">
          {label}
        </label>
        <div className="flex items-baseline gap-1 shrink-0">
          <input
            type="number"
            value={Number(value.toFixed(places))}
            min={min} max={max} step={step}
            onChange={e => {
              const n = Number(e.target.value)
              if (!Number.isNaN(n)) onChange(clamp(n))
            }}
            className="w-14 bg-transparent text-right text-xs font-semibold text-white
                       border-b border-transparent hover:border-navy-700
                       focus:border-navy-500 focus:outline-none tabular-nums
                       [appearance:textfield]
                       [&::-webkit-outer-spin-button]:appearance-none
                       [&::-webkit-inner-spin-button]:appearance-none"
          />
          {unit && <span className="text-[10px] text-navy-500">{unit}</span>}
        </div>
      </div>

      <input
        id={id}
        type="range"
        min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer
                   focus:outline-none focus-visible:ring-2 focus-visible:ring-navy-500/50
                   [&::-webkit-slider-thumb]:appearance-none
                   [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-3.5
                   [&::-webkit-slider-thumb]:rounded-full
                   [&::-webkit-slider-thumb]:bg-white
                   [&::-webkit-slider-thumb]:shadow
                   [&::-webkit-slider-thumb]:transition-transform
                   [&::-webkit-slider-thumb]:hover:scale-125
                   [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:w-3.5
                   [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-white
                   [&::-moz-range-thumb]:border-0"
        style={{
          background: `linear-gradient(to right, #3d5ca8 ${pct}%, #132354 ${pct}%)`,
        }}
      />
    </div>
  )
}
