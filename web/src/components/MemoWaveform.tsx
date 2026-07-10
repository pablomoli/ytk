import { useEffect, useRef, useState } from 'react'
import type { MouseEvent } from 'react'

let activePlayer: HTMLAudioElement | null = null
let activeCanvas: HTMLCanvasElement | null = null
let activePeaks: number[] = []

function drawWave(canvas: HTMLCanvasElement, peaks: number[], fraction: number) {
  const context = canvas.getContext('2d')
  if (!context || !peaks.length) return
  const width = canvas.offsetWidth * 2
  const height = 96
  canvas.width = width
  canvas.height = height
  const barWidth = width / peaks.length
  context.clearRect(0, 0, width, height)
  peaks.forEach((peak, index) => {
    context.fillStyle = index / peaks.length < fraction ? '#4ade80' : '#31543f'
    const barHeight = Math.max(4, peak * height * 0.92)
    context.fillRect(index * barWidth + barWidth * 0.18, (height - barHeight) / 2, barWidth * 0.64, barHeight)
  })
}

async function peaksForAudio(audio: string): Promise<number[]> {
  const buffer = await (await fetch(`/api/memo-audio/${encodeURIComponent(audio)}`)).arrayBuffer()
  const AudioContextConstructor = window.AudioContext
  if (!AudioContextConstructor) throw new Error('AudioContext is unavailable')
  const context = new AudioContextConstructor()
  try {
    const decoded = await context.decodeAudioData(buffer)
    const data = decoded.getChannelData(0)
    const bars = 56
    const step = Math.floor(data.length / bars) || 1
    return Array.from({ length: bars }, (_, index) => {
      let maximum = 0
      for (let offset = index * step; offset < (index + 1) * step; offset += 32) {
        maximum = Math.max(maximum, Math.abs(data[offset] || 0))
      }
      return maximum
    })
  } finally {
    void context.close()
  }
}

export function MemoWaveform({ audio }: { audio: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const peaksRef = useRef<number[]>([])
  const [available, setAvailable] = useState(true)

  useEffect(() => {
    let cancelled = false
    const canvas = canvasRef.current
    if (!canvas) return

    void peaksForAudio(audio)
      .then((peaks) => {
        if (cancelled) return
        peaksRef.current = peaks
        drawWave(canvas, peaks, 0)
      })
      .catch(() => {
        if (!cancelled) setAvailable(false)
      })

    return () => {
      cancelled = true
      if (activeCanvas === canvas && activePlayer) {
        activePlayer.pause()
        activePlayer = null
        activeCanvas = null
        activePeaks = []
      }
    }
  }, [audio])

  if (!available) return null

  const handleClick = (event: MouseEvent<HTMLCanvasElement>) => {
    event.stopPropagation()
    const canvas = canvasRef.current
    if (!canvas || !peaksRef.current.length) return
    const fraction = event.nativeEvent.offsetX / canvas.offsetWidth

    if (activeCanvas === canvas && activePlayer) {
      activePlayer.currentTime = fraction * activePlayer.duration
      void activePlayer.play()
      return
    }

    if (activePlayer && activeCanvas) {
      activePlayer.pause()
      drawWave(activeCanvas, activePeaks, 0)
    }

    const player = new Audio(`/api/memo-audio/${encodeURIComponent(audio)}`)
    activePlayer = player
    activeCanvas = canvas
    activePeaks = peaksRef.current
    player.addEventListener('timeupdate', () => drawWave(canvas, peaksRef.current, player.currentTime / player.duration))
    player.addEventListener('ended', () => {
      drawWave(canvas, peaksRef.current, 0)
      if (activePlayer === player) {
        activePlayer = null
        activeCanvas = null
        activePeaks = []
      }
    })
    void player.play()
  }

  return <canvas ref={canvasRef} className="wave" onClick={handleClick} title="play memo" />
}
