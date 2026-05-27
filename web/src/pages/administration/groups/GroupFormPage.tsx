import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Layout from '../../../components/Layout'
import Tabs from '../../../components/ui/Tabs'
import FormField from '../../../components/ui/FormField'
import Switch from '../../../components/ui/Switch'
import { api } from '../../../services/api'
import { useToast } from '../../../contexts/ToastContext'

interface Module {
  id: number
  id_parent: number | null
  name: string
  slug: string
  actions: string | null
}

export default function GroupFormPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const isEdit = id !== 'new'
  const toast = useToast()

  const [form, setForm] = useState({ name: '', status: 1 })
  const [permissions, setPermissions] = useState<Record<string, string[]>>({})
  const [modules, setModules] = useState<Module[]>([])
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get('/si-modules').then(r => setModules(r.data)).catch(err => console.error('si-modules error:', err))
    if (isEdit) {
      api.get(`/groups/${id}`).then(r => {
        const g = r.data
        setForm({ name: g.name, status: g.status })
        setPermissions(g.permissions ?? {})
      }).catch(err => console.error('group fetch error:', err))
    }
  }, [id])

  function togglePermission(slug: string, action: string) {
    setPermissions(prev => {
      const current = prev[slug] ?? []
      const updated = current.includes(action) ? current.filter(a => a !== action) : [...current, action]
      return { ...prev, [slug]: updated }
    })
  }

  function toggleAll(slug: string, actions: string[]) {
    setPermissions(prev => {
      const current = prev[slug] ?? []
      const allChecked = actions.every(a => current.includes(a))
      return { ...prev, [slug]: allChecked ? [] : [...actions] }
    })
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.name.trim()) { setErrors({ name: 'Nome é obrigatório' }); return }
    setSaving(true)
    try {
      const payload = { ...form, permissions }
      if (isEdit) await api.put(`/groups/${id}`, payload)
      else await api.post('/groups', payload)
      toast.success(isEdit ? 'Grupo atualizado com sucesso!' : 'Grupo cadastrado com sucesso!')
      navigate('/administration/groups')
    } catch {
      toast.error('Erro ao salvar. Tente novamente.')
      setErrors({ submit: 'Erro ao salvar.' })
    } finally {
      setSaving(false)
    }
  }

  const parents = modules.filter(m => m.id_parent === null)
  const childrenOf = (parentId: number) => modules.filter(m => m.id_parent === parentId)

  return (
    <Layout title={isEdit ? 'Editar Grupo' : 'Novo Grupo'} description="Administração / Grupos">
      <form onSubmit={handleSubmit} className="w-full">
        <div className="rounded-xl border border-navy-800 p-6 lg:p-8" style={{ background: '#141920' }}>
          <Tabs tabs={[
            {
              label: 'Dados Gerais',
              content: (
                <div className="grid grid-cols-1 gap-5">
                  <FormField label="Nome do grupo" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="Ex: Administrador" error={errors.name} />
                  <Switch
                    label="Status"
                    description="Grupo ativo pode ser atribuído a usuários"
                    checked={form.status === 1}
                    onChange={v => setForm(f => ({ ...f, status: v ? 1 : 0 }))}
                  />
                  {errors.submit && <p className="text-red-400 text-sm">{errors.submit}</p>}
                </div>
              )
            },
            {
              label: 'Permissões',
              content: (
                <div className="space-y-3">
                  {parents.map(parent => {
                    const subs = childrenOf(parent.id)
                    const rows = subs.length > 0 ? subs : [parent]
                    return (
                      <div key={parent.id} className="rounded-lg border border-navy-800 overflow-hidden">
                        <div className="px-4 py-2.5 text-xs font-semibold text-navy-300 uppercase tracking-wider" style={{ background: '#1c2333' }}>
                          {parent.name}
                        </div>
                        <div className="divide-y divide-navy-900">
                          {rows.map(mod => {
                            const actions = (mod.actions ?? '').split(',').map(a => a.trim()).filter(Boolean)
                            if (!actions.length) return null
                            const current = permissions[mod.slug] ?? []
                            const allChecked = actions.every(a => current.includes(a))
                            return (
                              <div key={mod.id} className="px-4 py-4 flex flex-wrap items-center gap-x-8 gap-y-4">
                                <div className="w-28 text-sm font-medium text-navy-200 shrink-0">{mod.name}</div>
                                <div className="flex flex-wrap gap-x-6 gap-y-4 items-center">
                                  <Switch
                                    label="Todos"
                                    checked={allChecked}
                                    onChange={() => toggleAll(mod.slug, actions)}
                                  />
                                  {actions.map(action => (
                                    <Switch
                                      key={action}
                                      label={action.charAt(0).toUpperCase() + action.slice(1)}
                                      checked={current.includes(action)}
                                      onChange={() => togglePermission(mod.slug, action)}
                                    />
                                  ))}
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )
                  })}
                  {parents.length === 0 && (
                    <p className="text-center text-navy-500 text-sm py-8">Nenhum módulo cadastrado.</p>
                  )}
                </div>
              )
            }
          ]} />
        </div>

        <div className="flex flex-col-reverse sm:flex-row items-center gap-3 mt-6">
          <button type="button" onClick={() => navigate('/administration/groups')} className="w-full sm:w-auto px-6 py-3 text-sm font-medium text-navy-300 hover:text-white border border-navy-700 hover:border-navy-500 rounded-lg transition-colors">
            Cancelar
          </button>
          <button type="submit" disabled={saving} className="w-full sm:w-auto px-8 py-3 bg-navy-600 hover:bg-navy-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors">
            {saving ? 'Salvando...' : isEdit ? 'Salvar alterações' : 'Cadastrar grupo'}
          </button>
        </div>
      </form>
    </Layout>
  )
}
