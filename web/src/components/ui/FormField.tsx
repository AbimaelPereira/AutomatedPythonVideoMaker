interface Props extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string
  error?: string
}

export default function FormField({ label, error, ...props }: Props) {
  return (
    <div>
      <label className="block text-xs font-medium text-navy-300 mb-1.5">{label}</label>
      <input
        {...props}
        className={`w-full border rounded-lg px-3 py-2 text-sm text-white placeholder-navy-500 focus:outline-none transition-colors
          ${error ? 'border-red-500 bg-red-950' : 'border-navy-700 focus:border-navy-500'}
        `}
        style={error ? {} : { background: '#0d1117' }}
      />
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  )
}
