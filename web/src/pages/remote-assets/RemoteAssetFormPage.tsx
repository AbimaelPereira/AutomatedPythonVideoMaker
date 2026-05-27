import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Layout from '../../components/Layout'
import Tabs from '../../components/ui/Tabs'
import FormField from '../../components/ui/FormField'
import { api } from '../../services/api'
import { useToast } from '../../contexts/ToastContext'

export default function RemoteAssetFormPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const isEdit = id !== 'new'

  const [form, setForm] = useState({ name: '', slug: '', description: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (isEdit) {
      api.get(`/remote-assets/${id}`).then(r => {
        const a = r.data
        setForm({ name: a.name, slug: a.slug, description: a.description ?? '' })
      }).catch(() => navigate('/remote-assets/assets'))
    }
  }, [id])

  function slugify(text: string) {
    return text.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
  }

  function validate() {
    const e: Record<string, string> = {}
    if (!form.name.trim()) e.name = 'Nome é obrigatório'
    if (!form.slug.trim()) e.slug = 'Slug é obrigatório'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    setSaving(true)
    try {
      if (isEdit) await api.put(`/remote-assets/${id}`, form)
      else await api.post('/remote-assets', form)
      toast.success(isEdit ? 'Asset atualizado com sucesso!' : 'Asset cadastrado com sucesso!')
      navigate('/remote-assets/assets')
    } catch {
      toast.error('Erro ao salvar. Verifique se o slug já existe.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Layout title={isEdit ? 'Editar Asset' : 'Novo Asset'} description="Remote Assets">
      <form onSubmit={handleSubmit} className="w-full">
        <div className="rounded-xl border border-navy-800 p-6 lg:p-8" style={{ background: '#141920' }}>
          <Tabs tabs={[{
            label: 'Dados Gerais',
            content: (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                <FormField
                  label="Nome"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value, slug: isEdit ? f.slug : slugify(e.target.value) }))}
                  placeholder="Ex: Fundos Natureza"
                  error={errors.name}
                />
                <FormField
                  label="Slug"
                  value={form.slug}
                  onChange={e => setForm(f => ({ ...f, slug: slugify(e.target.value) }))}
                  placeholder="Ex: fundos-natureza"
                  error={errors.slug}
                />
                <div className="sm:col-span-2">
                  <label className="block text-xs font-medium text-navy-300 mb-1.5">Descrição</label>
                  <textarea
                    value={form.description}
                    onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                    placeholder="Descrição opcional do asset..."
                    rows={3}
                    className="w-full border border-navy-700 rounded-lg px-3 py-2 text-sm text-white placeholder-navy-500 focus:outline-none focus:border-navy-500 resize-none"
                    style={{ background: '#0d1117' }}
                  />
                </div>
              </div>
            )
          }]} />
        </div>

        <div className="flex flex-col-reverse sm:flex-row items-center gap-3 mt-6">
          <button type="button" onClick={() => navigate('/remote-assets/assets')} className="w-full sm:w-auto px-6 py-3 text-sm font-medium text-navy-300 hover:text-white border border-navy-700 hover:border-navy-500 rounded-lg transition-colors">
            Cancelar
          </button>
          <button type="submit" disabled={saving} className="w-full sm:w-auto px-8 py-3 bg-navy-600 hover:bg-navy-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors">
            {saving ? 'Salvando...' : isEdit ? 'Salvar alterações' : 'Cadastrar asset'}
          </button>
        </div>
      </form>
    </Layout>
  )
}
