import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import * as LucideIcons from 'lucide-react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../services/api'

interface Module {
  id: number
  id_parent: number | null
  name: string
  slug: string
  icon: string | null
}

function DynamicIcon({ name, size = 15 }: { name: string; size?: number }) {
  const Icon = (LucideIcons as any)[name]
  if (!Icon) return <LucideIcons.Box size={size} />
  return <Icon size={size} />
}

function ParentItem({ mod, children, onClose }: { mod: Module; children: Module[]; onClose?: () => void }) {
  const location = useLocation()
  const isAnyChildActive = children.some(c => location.pathname.startsWith(`/${c.slug}`))
  const [open, setOpen] = useState(isAnyChildActive)

  return (
    <div>
      <button
        onClick={() => setOpen(o => !o)}
        className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
          isAnyChildActive ? 'text-white bg-navy-800' : 'text-navy-300 hover:bg-navy-900 hover:text-white'
        }`}
      >
        <div className="flex items-center gap-3">
          <DynamicIcon name={mod.icon ?? 'Box'} />
          {mod.name}
        </div>
        {open ? <ChevronDown size={13} className="opacity-50" /> : <ChevronRight size={13} className="opacity-50" />}
      </button>
      {open && (
        <div className="ml-3 mt-0.5 pl-3 border-l border-navy-800 space-y-0.5">
          {children.map(child => (
            <NavLink
              key={child.id}
              to={`/${child.slug}`}
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive ? 'text-white bg-navy-800' : 'text-navy-400 hover:text-white hover:bg-navy-900'
                }`
              }
            >
              <DynamicIcon name={child.icon ?? 'Dot'} size={13} />
              {child.name}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Sidebar({ onClose }: { onClose?: () => void }) {
  const { user, logout } = useAuth()
  const [modules, setModules] = useState<Module[]>([])

  useEffect(() => {
    api.get('/modules').then(res => setModules(res.data)).catch(() => {})
  }, [])

  const parents = modules.filter(m => m.id_parent === null)
  const children = (pid: number) => modules.filter(m => m.id_parent === pid)

  return (
    <aside className="w-56 flex flex-col min-h-screen border-r border-navy-900" style={{ background: '#141920' }}>
      <div className="px-5 h-16 flex items-center border-b border-navy-900">
        <span className="text-base font-bold tracking-tight text-white">Anonimo</span>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {parents.map(mod => {
          const subs = children(mod.id)
          if (subs.length > 0) {
            return <ParentItem key={mod.id} mod={mod} children={subs} onClose={onClose} />
          }
          return (
            <NavLink
              key={mod.id}
              to={`/${mod.slug}`}
              onClick={onClose}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive ? 'bg-navy-800 text-white' : 'text-navy-300 hover:bg-navy-900 hover:text-white'
                }`
              }
            >
              <DynamicIcon name={mod.icon ?? 'Box'} />
              {mod.name}
            </NavLink>
          )
        })}
      </nav>

      <div className="px-4 py-4 border-t border-navy-900">
        <p className="text-xs text-navy-400 truncate mb-2">{user?.email}</p>
        <button onClick={logout} className="text-xs text-navy-400 hover:text-white transition-colors">Sair</button>
      </div>
    </aside>
  )
}
