import { useEffect, useState } from 'react'

/**
 * Retorna uma versão "atrasada" de `value` que só atualiza após `delay` ms sem
 * mudanças. Útil para disparar requisições de preview sem fazer uma a cada
 * tecla/ajuste de slider.
 */
export function useDebouncedValue<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(id)
  }, [value, delay])

  return debounced
}
