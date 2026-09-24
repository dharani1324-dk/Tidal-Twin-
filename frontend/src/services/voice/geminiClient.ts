/**
 * TIDE Voice Agent - Gemini Live WebSocket client (browser audio transport).
 *
 * Handles ONLY the transport: microphone capture (16 kHz PCM16 mic feed),
 * Gemini Live WebSocket frames, PCM16 (24 kHz) playback and input/output audio
 * levels.  Session logic lives in voiceSession.ts; nothing here knows about
 * TidalTwin tools.
 *
 * Flow: the backend mints a short-lived ephemeral token (locking the model,
 * system prompt, tools and voice onto it via the provisioning API).  The
 * browser opens a direct WebSocket to Google with that token as
 * ``access_token`` and streams PCM16 audio.  No project API key ever reaches
 * the browser.
 */

export type RealtimeEventHandler = (event: Record<string, unknown>) => void

export interface AudioLevels {
  input: number  // 0..1
  output: number // 0..1
}

export interface GeminiConnectOptions {
  model: string
  ephemeralKey: string
  baseUrl?: string
  /**
   * The server-locked BidiGenerateContentSetup contract (system prompt, tools,
   * voice, transcription).  Sent as the first WS frame so the connection works
   * even when the mint had to fall back to an unlocked token.
   */
  setup?: Record<string, unknown> | null
}

const INPUT_RATE = 16000  // Gemini Live input audio: 16 kHz raw PCM16 LE
const OUTPUT_RATE = 24000 // Gemini Live output audio: always 24 kHz
const PCM_CHUNK_SAMPLES = INPUT_RATE / 10 // 100 ms frames
const LEVEL_TIMER_MS = 30

function toBase64(bytes: Uint8Array): string {
  let binary = ''
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i])
  return btoa(binary)
}

function decodePcmS16(base64: string): Int16Array {
  const binary = atob(base64)
  const out = new Int16Array(binary.length / 2)
  for (let i = 0; i < out.length; i += 1) {
    const lo = binary.charCodeAt(i * 2)
    const hi = binary.charCodeAt(i * 2 + 1)
    out[i] = (hi << 8) | lo
  }
  return out
}

export class GeminiClient {
  onEvent?: RealtimeEventHandler
  onAudioLevel?: (levels: AudioLevels) => void

  private ws: WebSocket | null = null
  private stream: MediaStream | null = null
  private audioCtx: AudioContext | null = null
  private inAnalyser: AnalyserNode | null = null
  private outAnalyser: AnalyserNode | null = null
  private micSource: MediaStreamAudioSourceNode | null = null
  private capture: ScriptProcessorNode | null = null
  private capturePcm: Int16Array[] = []
  private pendingSamples = 0

  private levelTimer: number | null = null
  private nextPlayTime = 0
  private closed = true
  private userClosed = false

  async connect(options: GeminiConnectOptions): Promise<void> {
    if (!options.ephemeralKey) throw new Error('voice: no ephemeral key')
    this.closed = false
    this.userClosed = false
    this.capturePcm = []
    this.pendingSamples = 0

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
    })
    this.stream = stream

    const AudioCtor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    const ctx = new AudioCtor()
    this.audioCtx = ctx
    if (ctx.state === 'suspended') await ctx.resume()

    this.inAnalyser = ctx.createAnalyser()
    this.inAnalyser.fftSize = 256
    this.micSource = ctx.createMediaStreamSource(stream)
    this.micSource.connect(this.inAnalyser)

    this.outAnalyser = ctx.createAnalyser()
    this.outAnalyser.fftSize = 256
    this.outAnalyser.connect(ctx.destination)

    const base = (options.baseUrl ?? 'https://generativelanguage.googleapis.com').replace(/\/$/, '')
    const url =
      `${base}/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained` +
      `?access_token=${encodeURIComponent(options.ephemeralKey)}`
    this.ws = new WebSocket(url)
    this.ws.onopen = () => this.sendSetup(options)
    this.ws.onmessage = (ev) => this.handleMessage(ev)
    this.ws.onerror = () => this.handleClose('websocket_error')
    this.ws.onclose = () => this.handleClose('closed')

    this.startCapture()
    this.startLevelTimer()
  }

  sendToolResponse(responses: { name: string; response: Record<string, unknown> }[]): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ toolResponse: { functionResponses: responses } }))
    }
  }

  /** Optimistic convenience for future text turns (the orb currently is voice-only). */
  sendSetupFrame(setup: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ setup }))
    }
  }

  stopAudio(): void {
    this.nextPlayTime = 0
  }

  async disconnect(): Promise<void> {
    this.userClosed = true
    this.closed = true
    if (this.levelTimer != null) {
      window.clearInterval(this.levelTimer)
      this.levelTimer = null
    }
    if (this.capture) {
      this.capture.onaudioprocess = null
      this.capture.disconnect()
      this.capture = null
    }
    if (this.ws) {
      try { this.ws.close() } catch { /* ignore */ }
      this.ws = null
    }
    this.stream?.getTracks().forEach((t) => t.stop())
    this.stream = null
    if (this.audioCtx) {
      await this.audioCtx.close().catch(() => undefined)
      this.audioCtx = null
    }
    this.micSource = null
    this.inAnalyser = null
    this.outAnalyser = null
  }

  get isClosed(): boolean {
    return this.closed
  }

  // -- transport -----------------------------------------------------------

  private sendSetup(options: GeminiConnectOptions): void {
    if (!this.ws) return
    const model = options.model.includes('/') ? options.model : `models/${options.model}`
    if (options.setup) {
      this.ws.send(JSON.stringify({ setup: { ...options.setup, model } }))
    } else {
      this.ws.send(
        JSON.stringify({
          setup: {
            model,
            generationConfig: { responseModalities: ['AUDIO'] },
          },
        }),
      )
    }
  }

  private handleMessage(ev: MessageEvent): void {
    let msg: Record<string, unknown>
    try {
      msg = JSON.parse(typeof ev.data === 'string' ? ev.data : '')
    } catch {
      return
    }
    if (msg.setupComplete) {
      this.onEvent?.({ type: 'gemini.session_ready' })
      return
    }
    if (msg.serverContent) this.handleServerContent(msg.serverContent as Record<string, unknown>)
    if (msg.toolCall) this.handleToolCall(msg.toolCall as Record<string, unknown>)
    if (msg.error) {
      const err = msg.error as { code?: unknown; message?: unknown }
      this.onEvent?.({
        type: 'error',
        code: typeof err.code === 'string' ? err.code : 'gemini_error',
        message: typeof err.message === 'string' ? err.message.slice(0, 200) : 'Gemini error',
      })
    }
  }

  private handleServerContent(sc: Record<string, unknown>): void {
    const parts = (sc.modelTurn as { parts?: unknown[] } | undefined)?.parts ?? []
    let toolParts = 0
    for (const part of parts) {
      const p = part as Record<string, unknown>
      const inline = p.inlineData as { data?: unknown } | undefined
      if (inline && typeof inline.data === 'string') {
        this.playInlineAudio(inline.data)
      }
      if (p.functionCall) {
        toolParts += 1
        const fn = p.functionCall as { name?: unknown; args?: unknown }
        this.onEvent?.({
          type: 'gemini.tool_call',
          calls: [{ name: fn.name ?? '', args: fn.args ?? {} }],
        })
      }
      if (typeof p.text === 'string' && p.text) {
        this.onEvent?.({ type: 'gemini.assistant_transcript.delta', delta: p.text })
      }
      if (p.transcript && typeof (p.transcript as { text?: unknown }).text === 'string') {
        this.onEvent?.({
          type: 'conversation.item.input_audio_transcription.completed',
          transcript: (p.transcript as { text: string }).text,
        })
      }
    }
    if (toolParts === 0 && parts.length > 0 && sc.turn === 'user') {
      this.onEvent?.({ type: 'gemini.user_turn' })
    }
    if (sc.turnComplete) {
      this.onEvent?.({ type: 'gemini.turn_complete' })
    }
    if (sc.interrupted) {
      this.onEvent?.({ type: 'gemini.interrupted' })
    }
  }

  private handleToolCall(tc: Record<string, unknown>): void {
    const calls = (tc.functionCalls as { name?: unknown; args?: unknown }[] | undefined) ?? []
    if (calls.length === 0) return
    this.onEvent?.({
      type: 'gemini.tool_call',
      calls: calls.map((c) => ({ name: c.name ?? '', args: c.args ?? {} })),
    })
  }

  private handleClose(kind: string): void {
    if (this.userClosed) return
    this.closed = true
    this.onEvent?.({ type: 'error', code: 'connection_closed', message: kind })
  }

  // -- audio in ------------------------------------------------------------

  private startCapture(): void {
    const ctx = this.audioCtx
    if (!ctx) return
    const capture = ctx.createScriptProcessor(2048, 1, 1)
    this.capture = capture
    const rate = ctx.sampleRate
    const ratio = rate / INPUT_RATE
    // Keep the input analyser fed (levels) and resample+encode mic PCM16.
    this.micSource?.connect(capture)
    capture.onaudioprocess = (ev) => {
      const input = ev.inputBuffer.getChannelData(0)
      const resampled = new Float32Array(Math.floor((input.length / ratio)))
      for (let i = 0; i < resampled.length; i += 1) {
        const src = i * ratio
        const lo = Math.floor(src)
        const hi = Math.min(lo + 1, input.length - 1)
        const frac = src - lo
        resampled[i] = input[lo] * (1 - frac) + input[hi] * frac
      }
      const pcm = new Int16Array(resampled.length)
      for (let i = 0; i < resampled.length; i += 1) {
        const s = Math.max(-1, Math.min(1, resampled[i]))
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff
      }
      this.capturePcm.push(pcm)
      this.pendingSamples += pcm.length
      this.flushCapture()
    }
    capture.connect(ctx.destination)
  }

  private flushCapture(): void {
    if (!this.ws || this.pendingSamples < PCM_CHUNK_SAMPLES) return
    const total = Math.floor(this.pendingSamples / PCM_CHUNK_SAMPLES) * PCM_CHUNK_SAMPLES
    const joined = new Int16Array(total)
    let offset = 0
    const kept: Int16Array[] = []
    let keptSamples = 0
    for (const buf of this.capturePcm) {
      if (offset + buf.length <= total) {
        joined.set(buf, offset)
        offset += buf.length
      } else {
        const take = Math.max(0, total - offset)
        if (take > 0) {
          joined.set(buf.subarray(0, take), offset)
          offset += take
        }
        kept.push(buf.subarray(take))
        keptSamples += buf.length - take
      }
    }
    this.capturePcm = kept
    this.pendingSamples = keptSamples
    if (total === 0) return
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(
        JSON.stringify({
          realtimeInput: { audio: { mimeType: 'audio/pcm;rate=16000', data: toBase64(new Uint8Array(joined.buffer)) } },
        }),
      )
    }
  }

  // -- audio out -----------------------------------------------------------

  private playInlineAudio(base64: string): void {
    try {
      this.enqueueSamples(decodePcmS16(base64))
    } catch (err) {
      console.error('[voice-client] PCM decode failed', err)
    }
  }

  private enqueueSamples(samples: Int16Array): void {
    const ctx = this.audioCtx
    if (!ctx || samples.length === 0) return
    const float = new Float32Array(samples.length)
    for (let i = 0; i < samples.length; i += 1) float[i] = samples[i] / 32768
    const duration = float.length / OUTPUT_RATE
    if (this.nextPlayTime < ctx.currentTime + 0.05) {
      this.nextPlayTime = ctx.currentTime + 0.05
    }
    const buffer = ctx.createBuffer(1, float.length, OUTPUT_RATE)
    buffer.copyToChannel(float, 0)
    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.connect(this.outAnalyser ?? ctx.destination)
    source.start(this.nextPlayTime)
    this.nextPlayTime += duration
  }

  // -- levels --------------------------------------------------------------

  private startLevelTimer(): void {
    if (this.levelTimer != null) return
    this.levelTimer = window.setInterval(() => {
      if (!this.inAnalyser || !this.outAnalyser) return
      this.onAudioLevel?.({
        input: this.readLevel(this.inAnalyser),
        output: this.readLevel(this.outAnalyser),
      })
    }, LEVEL_TIMER_MS)
  }

  private readLevel(analyser: AnalyserNode): number {
    const data = new Uint8Array(analyser.frequencyBinCount)
    analyser.getByteFrequencyData(data)
    let sum = 0
    for (let i = 0; i < data.length; i += 1) sum += data[i]
    const avg = sum / data.length / 255
    return avg >= 0.02 ? Math.min(1, avg * 3) : 0
  }
}