import { useRef, useState, useCallback, useEffect } from 'react'

export interface PlayerState {
  playing: boolean
  currentTime: number
  duration: number
  range: { start: number; end: number } | null
  ready: boolean
}

export function useAudioPlayer(audioSrc: string) {
  const audioRef  = useRef<HTMLAudioElement | null>(null)
  const rangeRef  = useRef<{ start: number; end: number } | null>(null)
  const readyRef  = useRef(false)

  const [state, setState] = useState<PlayerState>({
    playing: false, currentTime: 0, duration: 0, range: null, ready: false,
  })

  useEffect(() => {
    if (!audioSrc) return

    const audio = new Audio()
    audio.preload = 'auto'
    audioRef.current = audio
    readyRef.current = false
    rangeRef.current = null

    setState({ playing: false, currentTime: 0, duration: 0, range: null, ready: false })

    const onMetadata  = () => setState(s => ({ ...s, duration: audio.duration }))
    const onCanPlay   = () => { readyRef.current = true; setState(s => ({ ...s, ready: true })) }
    const onEnded     = () => setState(s => ({ ...s, playing: false }))
    const onTimeUpdate = () => {
      const t = audio.currentTime
      const r = rangeRef.current
      if (r && t >= r.end) {
        audio.pause()
        audio.currentTime = r.start
        setState(s => ({ ...s, playing: false, currentTime: r.start }))
        return
      }
      setState(s => ({ ...s, currentTime: t }))
    }
    const onPlay  = () => setState(s => ({ ...s, playing: true }))
    const onPause = () => setState(s => ({ ...s, playing: false }))

    audio.addEventListener('loadedmetadata', onMetadata)
    audio.addEventListener('canplay',        onCanPlay)
    audio.addEventListener('ended',          onEnded)
    audio.addEventListener('timeupdate',     onTimeUpdate)
    audio.addEventListener('play',           onPlay)
    audio.addEventListener('pause',          onPause)

    audio.src = audioSrc
    audio.load()

    return () => {
      audio.pause()
      audio.src = ''
      audio.removeEventListener('loadedmetadata', onMetadata)
      audio.removeEventListener('canplay',        onCanPlay)
      audio.removeEventListener('ended',          onEnded)
      audio.removeEventListener('timeupdate',     onTimeUpdate)
      audio.removeEventListener('play',           onPlay)
      audio.removeEventListener('pause',          onPause)
    }
  }, [audioSrc])

  const play = useCallback((range?: { start: number; end: number }) => {
    const audio = audioRef.current
    if (!audio) return
    if (range) {
      rangeRef.current = range
      setState(s => ({ ...s, range }))
      if (audio.currentTime < range.start || audio.currentTime >= range.end) {
        audio.currentTime = range.start
      }
    } else {
      rangeRef.current = null
      setState(s => ({ ...s, range: null }))
    }
    audio.play().catch(() => {})
  }, [])

  const pause = useCallback(() => {
    audioRef.current?.pause()
  }, [])

  const seek = useCallback((time: number) => {
    const audio = audioRef.current
    if (!audio) return
    audio.currentTime = time
  }, [])

  const seekAndPlay = useCallback((time: number) => {
    const audio = audioRef.current
    if (!audio) return
    rangeRef.current = null
    setState(s => ({ ...s, range: null }))
    audio.currentTime = time
    audio.play().catch(() => {})
  }, [])

  return { state, play, pause, seek, seekAndPlay, audioRef }
}
