interface Props {
  active: boolean
}

export default function Badge({ active }: Props) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
      active ? 'bg-emerald-900 text-emerald-300' : 'bg-red-900 text-red-300'
    }`}>
      {active ? 'Ativo' : 'Inativo'}
    </span>
  )
}
