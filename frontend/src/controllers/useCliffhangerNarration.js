import { useCallback, useEffect, useRef, useState } from 'react'

import { narrateCliffhanger } from '../lib/api'
import { audioUrlFromBase64, revokeAudioUrl } from '../utils/audio'

/**
 * Owns the "hear the difference" audio for the Cliffhanger Optimizer.
 *
 * Synthesizes both endings once (one backend call), holds their object URLs, and
 * plays them through a single shared `<audio>` element so only one clip is ever
 * audible. Playback is user-gesture initiated — there is no autoplay-on-load.
 *
 * Exposes:
 *   status   'idle' | 'loading' | 'ready' | 'error'
 *   error    message string when status === 'error'
 *   clips    { original:{url,mime,engine,voice,style}, optimized:{...} } | null
 *   playing  null | 'original' | 'optimized'
 *   progress 0-100 for the currently playing clip
 *   generate(original, optimized, { autoplay })  synthesize both endings
 *   playSequence()  play original, then optimized, back to back
 *   playOne(key)    play just one clip
 *   stop()          stop playback
 *   reset()         drop clips + revoke URLs (call when the source text changes)
 */
export function useCliffhangerNarration() {
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState(null)
  const [clips, setClips] = useState(null)
  const [playing, setPlaying] = useState(null)
  const [progress, setProgress] = useState(0)

  const audioRef = useRef(null)
  const urlsRef = useRef([]) // object URLs pending revocation
  const clipsRef = useRef(null) // latest clips, for sequencing without stale closures
  const seqRef = useRef(false) // whether an A/B "play both" sequence is active
  const reqRef = useRef(0) // guards against out-of-order responses

  const ensureAudio = () => {
    if (!audioRef.current) audioRef.current = new Audio()
    return audioRef.current
  }

  const detach = (audio) => {
    audio.onended = null
    audio.ontimeupdate = null
    audio.onerror = null
  }

  const stop = useCallback(() => {
    seqRef.current = false
    const audio = audioRef.current
    if (audio) {
      detach(audio)
      audio.pause()
      try {
        audio.currentTime = 0
      } catch {
        /* ignore: not seekable yet */
      }
    }
    setPlaying(null)
    setProgress(0)
  }, [])

  const revokeAll = useCallback(() => {
    urlsRef.current.forEach(revokeAudioUrl)
    urlsRef.current = []
  }, [])

  // Play a single clip; when `thenOptimized` and a sequence is active, chain to
  // the optimized clip on end so the A/B plays back to back.
  const playClip = useCallback((key, { thenOptimized = false } = {}) => {
    const clip = clipsRef.current?.[key]
    if (!clip?.url) return
    const audio = ensureAudio()
    detach(audio)
    audio.pause()
    audio.src = clip.url
    audio.currentTime = 0
    setPlaying(key)
    setProgress(0)
    audio.ontimeupdate = () => {
      if (audio.duration > 0) setProgress((audio.currentTime / audio.duration) * 100)
    }
    audio.onended = () => {
      if (thenOptimized && seqRef.current) {
        playClip('optimized')
        return
      }
      seqRef.current = false
      setPlaying(null)
      setProgress(0)
    }
    audio.onerror = () => {
      seqRef.current = false
      setPlaying(null)
      setProgress(0)
      setError('Playback failed.')
    }
    audio.play().catch(() => {
      // Autoplay policy or a transient decode issue — surface as stopped, not a crash.
      seqRef.current = false
      setPlaying(null)
    })
  }, [])

  const playOne = useCallback(
    (key) => {
      seqRef.current = false
      playClip(key)
    },
    [playClip],
  )

  const playSequence = useCallback(() => {
    seqRef.current = true
    playClip('original', { thenOptimized: true })
  }, [playClip])

  const generate = useCallback(
    async (original, optimized, { autoplay = false } = {}) => {
      const id = (reqRef.current += 1)
      setStatus('loading')
      setError(null)
      try {
        const res = await narrateCliffhanger({ original, optimized })
        if (id !== reqRef.current) return // superseded by a newer request
        revokeAll()
        const build = (clip) => {
          if (!clip?.audio_base64) return { url: null, ...clip }
          const url = audioUrlFromBase64(clip.audio_base64, clip.mime)
          if (url) urlsRef.current.push(url)
          return { url, mime: clip.mime, engine: clip.engine, voice: clip.voice, style: clip.style }
        }
        const next = { original: build(res.original), optimized: build(res.optimized) }
        clipsRef.current = next
        setClips(next)
        setStatus('ready')
        if (autoplay && id === reqRef.current) {
          seqRef.current = true
          playClip('original', { thenOptimized: true })
        }
      } catch (err) {
        if (id !== reqRef.current) return
        setStatus('error')
        setError(err.message || 'Could not voice the endings.')
      }
    },
    [playClip, revokeAll],
  )

  const reset = useCallback(() => {
    reqRef.current += 1 // invalidate any in-flight synthesis
    stop()
    revokeAll()
    clipsRef.current = null
    setClips(null)
    setStatus('idle')
    setError(null)
  }, [stop, revokeAll])

  // Pause and free audio URLs on unmount.
  useEffect(
    () => () => {
      const audio = audioRef.current
      if (audio) {
        detach(audio)
        audio.pause()
      }
      urlsRef.current.forEach(revokeAudioUrl)
      urlsRef.current = []
    },
    [],
  )

  return { status, error, clips, playing, progress, generate, playSequence, playOne, stop, reset }
}
