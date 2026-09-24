/**
 * TIDE Voice Agent - OpenAI Realtime WebRTC client (browser audio transport).
 *
 * Handles ONLY the transport: microphone capture, peer connection, data
 * channel events, PCM16 playback and input/output audio levels. Session logic
 * lives in voiceSession.ts; nothing here knows about TidalTwin tools.
 *
 * Flow: browser creates an SDP offer and POSTs it as application/sdp to
 * https://api.openai.com/v1/realtime/calls with the EPHEMERAL key (General
 * Availability connect endpoint; the legacy ?model= endpoint is gone). The
 * backend-issued ephemeral key is short-lived and cannot touch project data.
 */

export type RealtimeEventHandler = (event: Record<string, unknown>) => void

export interface AudioLevels {
  input: number  // 0..1
  output: number // 0..1
}

export interface RealtimeConnectOptions {
  model: string
  ephemeralKey: string
  baseUrl?: string
}

const CHUNK_MS = 30

export class RealtimeClient {
  onEvent?: RealtimeEventHandler
  onAudioLevel?: (levels: AudioLevels) => void

  private pc: RTCPeerConnection | null = null
  private dc: RTCDataChannel | null = null
  private stream: MediaStream | null = null
  private audioCtx: AudioContext | null = null
  private inAnalyser: AnalyserNode | null = null
  private outAnalyser: AnalyserNode | null = null
  private micSource: MediaStreamAudioSourceNode | null = null
  private remoteElement: HTMLAudioElement | null = null
  private outputSource: MediaStreamAudioSourceNode | null = null

  private pcmBuffers: Int16Array[] = []
  private levelTimer: number | null = null
  private closed = true

  async connect(options: RealtimeConnectOptions): Promise<void> {
    if (!options.ephemeralKey) throw new Error('voice: no ephemeral key')
    this.closed = false
    this.pcmBuffers = []

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
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

    this.remoteElement = new Audio()
    this.remoteElement.autoplay = true
    const remoteStream = new MediaStream()
    this.outputSource = ctx.createMediaStreamSource(remoteStream)
    this.outAnalyser = ctx.createAnalyser()
    this.outAnalyser.fftSize = 256
    this.outputSource.connect(this.outAnalyser)
    // keep analyser feeding the destination so levels update even silently
    this.outAnalyser.connect(ctx.destination)

    const pc = new RTCPeerConnection()
    this.pc = pc

    this.dc = pc.createDataChannel('oai-events', { ordered: true })
    this.dc.addEventListener('message', (ev) => this.handleDataChannelMessage(ev))

    pc.addTransceiver('audio', { direction: 'sendrecv' })
    stream.getAudioTracks().forEach((track) => pc.addTrack(track, stream))

    pc.ontrack = (event) => {
      for (const track of event.streams[0]?.getAudioTracks() ?? [event.track]) {
        remoteStream.addTrack(track)
      }
    }

    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    const url = `${(options.baseUrl ?? 'https://api.openai.com/v1').replace(/\/$/, '')}/realtime/calls`
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${options.ephemeralKey}`,
        'Content-Type': 'application/sdp',
      },
      body: offer.sdp ?? '',
    })
    if (!res.ok) {
      throw new Error(`voice: OpenAI SDP exchange failed (HTTP ${res.status})`)
    }
    const sdp = await res.text()
    await pc.setRemoteDescription({ type: 'answer', sdp })

    this.startLevelTimer()
  }

  sendEvent(event: Record<string, unknown>): void {
    if (this.dc?.readyState === 'open') {
      this.dc.send(JSON.stringify(event))
    }
  }

  /** Audio output PCM16 (from response.output_audio.delta) is accumulated and flushed
   *  on output_audio.done / output_audio.flushed into the output analyser. */
  acceptAudio(base64: string | undefined): void {
    if (!base64) return
    try {
      this.pcmBuffers.push(this.decodePcmS16(base64))
    } catch (err) {
      console.error('[voice-client] PCM decode failed', err)
    }
  }

  flushAudio(): void {
    if (this.pcmBuffers.length === 0 || !this.audioCtx) return
    const total = this.pcmBuffers.reduce((n, b) => n + b.length, 0)
    const joined = new Int16Array(total)
    let offset = 0
    for (const buf of this.pcmBuffers) {
      joined.set(buf, offset)
      offset += buf.length
    }
    this.pcmBuffers = []
    this.playPcm16(joined)
  }

  stopAudio(): void {
    if (this.pcmBuffers.length === 0) return
    this.pcmBuffers = []
  }

  async disconnect(): Promise<void> {
    this.closed = true
    if (this.levelTimer != null) {
      window.clearInterval(this.levelTimer)
      this.levelTimer = null
    }
    this.dc?.close()
    this.dc = null
    if (this.pc) {
      this.pc.ontrack = null
      this.pc.onicecandidate = null
      this.pc.close()
      this.pc = null
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
    this.outputSource = null
    this.remoteElement = null
  }

  private handleDataChannelMessage(ev: MessageEvent<string>): void {
    let data: Record<string, unknown>
    try {
      data = JSON.parse(ev.data as string)
    } catch {
      return
    }
    if (data.type === 'response.output_audio.delta' && typeof data.delta === 'string') {
      this.acceptAudio(data.delta)
      return
    }
    if (data.type === 'response.output_audio.done' || data.type === 'response.output_audio.flushed') {
      this.flushAudio()
    }
    this.onEvent?.(data)
  }

  private decodePcmS16(base64: string): Int16Array {
    const binary = atob(base64)
    const out = new Int16Array(binary.length / 2)
    for (let i = 0; i < out.length; i += 1) {
      const lo = binary.charCodeAt(i * 2)
      const hi = binary.charCodeAt(i * 2 + 1)
      out[i] = (hi << 8) | lo
    }
    return out
  }

  private playPcm16(samples: Int16Array): void {
    const ctx = this.audioCtx
    if (!ctx) return
    const float = new Float32Array(samples.length)
    for (let i = 0; i < samples.length; i += 1) float[i] = samples[i] / 32768
    const buffer = ctx.createBuffer(1, float.length, 24000)
    buffer.copyToChannel(float, 0)
    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.connect(this.outAnalyser ?? ctx.destination)
    source.start()
  }

  private startLevelTimer(): void {
    if (this.levelTimer != null) return
    this.levelTimer = window.setInterval(() => {
      if (!this.inAnalyser || !this.outAnalyser) return
      this.onAudioLevel?.({
        input: this.readLevel(this.inAnalyser),
        output: this.readLevel(this.outAnalyser),
      })
    }, CHUNK_MS)
  }

  private readLevel(analyser: AnalyserNode): number {
    const data = new Uint8Array(analyser.frequencyBinCount)
    analyser.getByteFrequencyData(data)
    let sum = 0
    for (let i = 0; i < data.length; i += 1) sum += data[i]
    const avg = sum / data.length / 255
    return avg >= 0.02 ? Math.min(1, avg * 3) : 0
  }

  get isClosed(): boolean {
    return this.closed
  }
}