import { useEffect, useRef, useState } from 'react'

import { Button, Icon } from '../primitives'

/** Extract the YouTube video id from a watch / youtu.be / embed URL. */
function youtubeId(url) {
  if (!url) return null
  try {
    const u = new URL(url)
    if (u.searchParams.get('v')) return u.searchParams.get('v')
    if (u.hostname.includes('youtu.be')) return u.pathname.slice(1) || null
    const parts = u.pathname.split('/').filter(Boolean)
    const i = parts.indexOf('embed')
    if (i >= 0 && parts[i + 1]) return parts[i + 1]
  } catch {
    /* not a URL — nothing to embed */
  }
  return null
}

// The IFrame Player API, loaded once and shared by every player on the page.
let ytReady = null
function loadYouTubeApi() {
  if (window.YT && window.YT.Player) return Promise.resolve(window.YT)
  if (ytReady) return ytReady
  ytReady = new Promise((resolve) => {
    const prev = window.onYouTubeIframeAPIReady
    window.onYouTubeIframeAPIReady = () => {
      if (typeof prev === 'function') prev()
      resolve(window.YT)
    }
    if (!document.querySelector('script[data-yt-api]')) {
      const tag = document.createElement('script')
      tag.src = 'https://www.youtube.com/iframe_api'
      tag.dataset.ytApi = '1'
      document.head.appendChild(tag)
    }
  })
  return ytReady
}

// onError codes: 101 & 150 mean the OWNER disabled embedding — nothing a page
// can override. 2/5/100 mean invalid / removed / private. Either way: stop
// showing a dead frame and route the listener to where it will actually play.
const EMBED_BLOCKED = new Set([101, 150])
const UNAVAILABLE = new Set([2, 5, 100])

/**
 * The shared inline player, used by both the shelves and the doorway.
 *
 * It plays the track through the YouTube IFrame Player API — real playback, not
 * a bare <iframe>. When the owner has blocked embedding (the one thing a page
 * genuinely cannot work around), the frame is REMOVED and replaced with a
 * "Play on YouTube" button, so a listener never stares at a "Video unavailable"
 * box. A missing/invalid video is handled the same way.
 *
 * `track`: { title, synopsis?/artist, audio_url, number? }
 */
export default function MoodPlayer({ track, onClose }) {
  const id = youtubeId(track?.audio_url)
  const hostRef = useRef(null)
  const playerRef = useRef(null)
  const [status, setStatus] = useState('loading') // loading | playing | blocked | unavailable

  useEffect(() => {
    if (!id) return undefined
    let cancelled = false
    setStatus('loading')

    loadYouTubeApi()
      .then((YT) => {
        if (cancelled || !hostRef.current) return
        if (playerRef.current) {
          try { playerRef.current.destroy() } catch { /* already gone */ }
        }
        // YT.Player replaces its target node, so give it a throwaway child.
        const mount = document.createElement('div')
        hostRef.current.replaceChildren(mount)
        playerRef.current = new YT.Player(mount, {
          videoId: id,
          width: '100%',
          height: '100%',
          playerVars: { autoplay: 1, rel: 0, playsinline: 1, modestbranding: 1 },
          events: {
            onReady: (e) => {
              if (cancelled) return
              setStatus('playing')
              try { e.target.playVideo() } catch { /* autoplay may need a tap */ }
            },
            onError: (e) => {
              if (cancelled) return
              setStatus(UNAVAILABLE.has(e.data) && !EMBED_BLOCKED.has(e.data) ? 'unavailable' : 'blocked')
            },
          },
        })
      })
      .catch(() => {
        if (!cancelled) setStatus('blocked')
      })

    return () => {
      cancelled = true
      if (playerRef.current) {
        try { playerRef.current.destroy() } catch { /* already gone */ }
        playerRef.current = null
      }
    }
  }, [id])

  if (!track) return null
  const artist = track.synopsis || track.artist
  const playable = status !== 'blocked' && status !== 'unavailable'

  return (
    <div
      style={{
        border: '1px solid var(--accent-line)',
        background: 'var(--accent-soft)',
        borderRadius: 'var(--radius-md)',
        padding: 14,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="label-upper" style={{ fontSize: 10, color: 'var(--accent-text-sm)' }}>
            {status === 'playing' ? 'Now playing' : 'Selected'}
            {track.number ? ` · track ${track.number}` : ''}
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--ink)', marginTop: 2 }}>
            {track.title}
          </div>
          {artist && (
            <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 2 }}>{artist}</div>
          )}
        </div>
        {onClose && (
          <Button variant="ghost" size="sm" onClick={onClose}>
            <Icon name="close" size={16} />
            Close
          </Button>
        )}
      </div>

      {/* Kept mounted whenever there is a video id (just hidden when blocked) so
          the player instance has a stable node to attach to across tracks. */}
      {id && (
        <div
          style={{
            position: 'relative',
            width: '100%',
            aspectRatio: '16 / 9',
            borderRadius: 'var(--radius-sm)',
            overflow: 'hidden',
            background: '#000',
            display: playable ? 'block' : 'none',
          }}
        >
          <div ref={hostRef} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} />
        </div>
      )}

      {!playable && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
            padding: '12px 14px',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--canvas)',
          }}
        >
          <span style={{ fontSize: 13, color: 'var(--muted)', flex: 1, minWidth: 180 }}>
            {status === 'blocked'
              ? 'The owner turned off inline play for this track — it can only play on YouTube.'
              : "This track isn't available to stream here."}
          </span>
          {track.audio_url && (
            <a href={track.audio_url} target="_blank" rel="noreferrer" style={{ textDecoration: 'none' }}>
              <Button variant="primary" size="sm">▶ Play on YouTube</Button>
            </a>
          )}
        </div>
      )}

      {playable && track.audio_url && (
        <a
          href={track.audio_url}
          target="_blank"
          rel="noreferrer"
          style={{ alignSelf: 'flex-start', fontSize: 13, fontWeight: 600, color: 'var(--accent-text-sm)' }}
        >
          Watch on YouTube ↗
        </a>
      )}
    </div>
  )
}
