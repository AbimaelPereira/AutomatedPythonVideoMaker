import ReactSelect, { Props as ReactSelectProps } from 'react-select'

interface Option {
  value: string | number
  label: string
}

interface Props extends Omit<ReactSelectProps<Option, false>, 'onChange'> {
  label?: string
  error?: string
  options: Option[]
  value?: string | number | null
  onChange: (value: string | number | null) => void
}

const styles = {
  control: (base: any, state: any) => ({
    ...base,
    background: '#0d1117',
    borderColor: state.isFocused ? '#3d5ca8' : '#1e3470',
    boxShadow: 'none',
    borderRadius: '0.5rem',
    minHeight: '42px',
    '&:hover': { borderColor: '#3d5ca8' },
  }),
  menu: (base: any) => ({
    ...base,
    background: '#141920',
    border: '1px solid #1e3470',
    borderRadius: '0.5rem',
    overflow: 'hidden',
  }),
  menuList: (base: any) => ({ ...base, padding: 0 }),
  option: (base: any, state: any) => ({
    ...base,
    background: state.isSelected ? '#1e3470' : state.isFocused ? '#1c2333' : 'transparent',
    color: state.isSelected ? '#fff' : '#c5d0e6',
    padding: '10px 14px',
    fontSize: '14px',
    cursor: 'pointer',
  }),
  singleValue: (base: any) => ({ ...base, color: '#fff', fontSize: '14px' }),
  placeholder: (base: any) => ({ ...base, color: '#5a76b5', fontSize: '14px' }),
  input: (base: any) => ({ ...base, color: '#fff', fontSize: '14px' }),
  indicatorSeparator: () => ({ display: 'none' }),
  dropdownIndicator: (base: any) => ({ ...base, color: '#3d5ca8', padding: '0 8px' }),
  clearIndicator: (base: any) => ({ ...base, color: '#3d5ca8' }),
  noOptionsMessage: (base: any) => ({ ...base, color: '#5a76b5', fontSize: '14px' }),
}

export default function Select({ label, error, options, value, onChange, placeholder, ...rest }: Props) {
  const selected = options.find(o => o.value === value) ?? null

  return (
    <div>
      {label && <label className="block text-xs font-medium text-navy-300 mb-1.5">{label}</label>}
      <ReactSelect
        options={options}
        value={selected}
        onChange={opt => onChange(opt?.value ?? null)}
        placeholder={placeholder ?? 'Selecione...'}
        styles={styles}
        isClearable
        isSearchable
        noOptionsMessage={() => 'Nenhum resultado'}
        {...rest}
      />
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  )
}
