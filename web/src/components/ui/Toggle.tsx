interface Props {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
  /** Texto de apoio abaixo do rótulo. */
  hint?: string
  disabled?: boolean
}

/**
 * Switch compacto para uso dentro de cards e listas.
 *
 * Difere do `Switch` global por caber numa linha de formulário dentro de um
 * card denso — o `Switch` usa espaçamento de página inteira e empurra demais
 * o layout quando aparece várias vezes seguidas.
 */
export default function Toggle({ label, checked, onChange, hint, disabled }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`w-full flex items-center justify-between gap-3 text-left group
                  ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
    >
      <span className="min-w-0">
        <span className={`block text-xs font-medium transition-colors
                          ${checked ? 'text-navy-100' : 'text-navy-400'}
                          ${!disabled && 'group-hover:text-white'}`}>
          {label}
        </span>
        {hint && (
          <span className="block text-[10px] leading-tight text-navy-500 mt-0.5">
            {hint}
          </span>
        )}
      </span>

      <span
        className={`relative inline-flex h-4 w-7 shrink-0 items-center rounded-full
                    transition-colors duration-200
                    ${checked ? 'bg-emerald-500' : 'bg-navy-700'}`}
      >
        <span
          className={`inline-block h-3 w-3 transform rounded-full bg-white shadow
                      transition-transform duration-200
                      ${checked ? 'translate-x-3.5' : 'translate-x-0.5'}`}
        />
      </span>
    </button>
  )
}
