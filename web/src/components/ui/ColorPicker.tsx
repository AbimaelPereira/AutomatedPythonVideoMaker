interface Props {
  label?: string
  value: string
  onChange: (value: string) => void
  /** Atalhos de cor mostrados abaixo do campo. */
  swatches?: string[]
  compact?: boolean
}

/** Paleta de partida — tons que aparecem com frequência em thumbnail. */
const DEFAULT_SWATCHES = [
  '#FFFFFF', '#000000', '#FFE24A', '#FF4A4A',
  '#4ADE80', '#38BDF8', '#A855F7', '#FB923C',
]

/**
 * Seletor de cor com amostra clicável, campo hex e atalhos.
 *
 * Os atalhos existem porque a paleta de uma thumbnail é pequena e repetitiva
 * (branco, preto, um amarelo de destaque); abrir o color picker do sistema
 * para cada uma delas é mais lento que um clique.
 */
export default function ColorPicker({
  label, value, onChange, swatches = DEFAULT_SWATCHES, compact = false,
}: Props) {
  return (
    <div>
      {label && (
        <label className="block text-xs font-medium text-navy-300 mb-1.5">{label}</label>
      )}

      <div className="flex items-center gap-2">
        {/* O <input type=color> fica invisível por cima da amostra: o nativo
            não é estilizável, mas continua sendo o que abre o seletor do SO. */}
        <div className="relative h-8 w-8 shrink-0">
          <div
            className="absolute inset-0 rounded-lg border border-navy-700 shadow-inner"
            style={{ background: value }}
          />
          <input
            type="color"
            value={/^#[0-9a-fA-F]{6}$/.test(value) ? value : '#000000'}
            onChange={e => onChange(e.target.value)}
            className="absolute inset-0 opacity-0 cursor-pointer"
            aria-label={label ?? 'Cor'}
          />
        </div>

        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          spellCheck={false}
          className="w-full min-w-0 border border-navy-700 rounded-lg px-2 py-1.5
                     text-xs font-mono text-white uppercase
                     focus:outline-none focus:border-navy-500 transition-colors"
          style={{ background: '#0d1117' }}
        />
      </div>

      {!compact && swatches.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {swatches.map(color => (
            <button
              key={color}
              type="button"
              onClick={() => onChange(color)}
              title={color}
              className={`h-4 w-4 rounded border transition-transform hover:scale-125
                          ${value.toUpperCase() === color.toUpperCase()
                            ? 'border-white' : 'border-navy-700'}`}
              style={{ background: color }}
            />
          ))}
        </div>
      )}
    </div>
  )
}
