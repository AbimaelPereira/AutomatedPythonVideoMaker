import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
})

function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.exp * 1000 < Date.now() + 30_000 // renova 30s antes de expirar
  } catch {
    return true
  }
}

export async function audioUrl(filePath: string): Promise<string> {
  let token = localStorage.getItem('token') ?? ''

  if (!token || isTokenExpired(token)) {
    const refreshToken = localStorage.getItem('refresh_token')
    if (refreshToken) {
      try {
        const { data } = await axios.post('/auth/refresh', { refresh_token: refreshToken })
        localStorage.setItem('token', data.access_token)
        localStorage.setItem('refresh_token', data.refresh_token)
        token = data.access_token
      } catch {
        localStorage.clear()
        window.location.href = '/login'
      }
    }
  }

  return `/api/reelscutter/audio?path=${encodeURIComponent(filePath)}&token=${encodeURIComponent(token)}`
}

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let isRefreshing = false
let queue: Array<(token: string) => void> = []

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    if (err.response?.status !== 401 || original._retry) {
      return Promise.reject(err)
    }

    const refreshToken = localStorage.getItem('refresh_token')
    if (!refreshToken) {
      localStorage.clear()
      window.location.href = '/login'
      return Promise.reject(err)
    }

    if (isRefreshing) {
      return new Promise((resolve) => {
        queue.push((token) => {
          original.headers.Authorization = `Bearer ${token}`
          resolve(api(original))
        })
      })
    }

    original._retry = true
    isRefreshing = true

    try {
      const { data } = await axios.post('/auth/refresh', { refresh_token: refreshToken })
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      queue.forEach((cb) => cb(data.access_token))
      queue = []
      original.headers.Authorization = `Bearer ${data.access_token}`
      return api(original)
    } catch {
      localStorage.clear()
      window.location.href = '/login'
      return Promise.reject(err)
    } finally {
      isRefreshing = false
    }
  }
)
