/**
 * TIDE Voice Agent - orchestration (browser).
 *
 * Owns the conversation loop on top of GeminiClient:
 *   microphone speech -> Gemini Live WebSocket -> function calls -> executeTool
 *   (real TidalTwin API adapters) -> toolResponse -> spoken answer.
 *
 * Fatal (setup) failures leave phase 'error'; per-call tool failures become a
 * tool response with status 'error' so the model can phrase a graceful
 * answer instead of fabricating data.
 */

import { askAssistant, createVoiceSession } from '../../api/client'
import { publishVoiceCommand } from './voiceBus.ts'
import { getVoiceContext } from './voiceContext.ts'
import { GeminiClient, type AudioLevels } from './geminiClient.ts'
import { executeTool } from './voiceTools.ts'
import type {
  VoiceMessage,
  VoicePhase,
  VoiceSessionBundle,
  VoiceToolInvocation,
} from './types.ts'

export interface VoiceSessionState {
  phase: VoicePhase
  error: string | null
  messages: VoiceMessage[]
  toolInvocations: VoiceToolInvocation[]
  webUsed: boolean
  session?: {
    id?: string | null
    model: string
    voice: string
    expiresAt?: number | null
  }
}

export function emptySessionState(): VoiceSessionState {
  return {
    phase: 'idle',
    error: null,
    messages: [],
    toolInvocations: [],
    webUsed: false,
  }
}

type OnState = (state: VoiceSessionState) => void

export class TideVoiceSession {
  private client: GeminiClient
  private tools: VoiceSessionBundle['tools'] = []
  private state: VoiceSessionState
  private onState: OnState
  private assistantBuffer = ''
  private started = false

  constructor(onState: OnState, onLevels?: (levels: AudioLevels) => void) {
    this.onState = onState
    this.state = emptySessionState()
    this.client = new GeminiClient()
    this.client.onEvent = (event) => this.handleEvent(event)
    this.client.onAudioLevel = onLevels ? (levels) => onLevels(levels) : undefined
  }

  get isConnected(): boolean {
    return !this.client.isClosed
  }

  async start(): Promise<void> {
    if (this.started && !this.client.isClosed) return
    this.started = true
    this.setState({ phase: 'connecting', error: null })
    try {
      const page = getVoiceContext().page ?? 'ocean_twin'
      const brief = `You are the ocean analyst aboard TidalTwin (Indian Ocean). The user is currently on the ${page} page.`
      const bundle: VoiceSessionBundle = await createVoiceSession({ brief })
      this.tools = bundle.tools ?? []
      this.setState({
        session: {
          id: bundle.session_id,
          model: bundle.model,
          voice: bundle.voice,
          expiresAt: bundle.ephemeral_key?.expires_at ?? null,
        },
      })
      await this.client.connect({
        model: bundle.model,
        ephemeralKey: bundle.ephemeral_key?.value ?? '',
        setup: bundle.setup ?? null,
      })
      this.setState({ phase: 'ready', error: null })
    } catch (error) {
      this.started = false
      this.setState({
        phase: 'error',
        error: error instanceof Error ? error.message : String(error),
      })
    }
  }

  stopAudio(): void {
    this.client.stopAudio()
  }

  async disconnect(): Promise<void> {
    await this.client.disconnect()
    this.started = false
    this.setState(emptySessionState())
  }

  clearTranscript(): void {
    this.setState({ messages: [], toolInvocations: [] })
  }

  /** Final fallback for the typed path: route to the assistant chat API. */
  async askText(text: string): Promise<string> {
    try {
      const payload = (await askAssistant(text)) as Record<string, unknown>
      const answer = typeof payload?.answer === 'string' ? payload.answer : ''
      return answer.trim()
    } catch {
      return ''
    }
  }

  private handleEvent(event: Record<string, unknown>): void {
    switch (event.type) {
      case 'gemini.session_ready':
        this.setState({ phase: 'ready', error: null })
        break
      case 'gemini.user_turn':
        this.setState({ phase: 'listening' })
        break
      case 'conversation.item.input_audio_transcription.completed': {
        const transcript = typeof event.transcript === 'string' ? event.transcript.trim() : ''
        if (!transcript) return
        this.pushMessage('user', transcript.slice(0, 400))
        this.setState({ phase: 'thinking' })
        break
      }
      case 'gemini.assistant_transcript.delta': {
        if (typeof event.delta === 'string') this.assistantBuffer += event.delta
        this.setState({ phase: 'speaking' })
        break
      }
      case 'gemini.interrupted':
        this.assistantBuffer = ''
        this.client.stopAudio()
        this.setState({ phase: 'thinking' })
        break
      case 'gemini.turn_complete': {
        const text = this.assistantBuffer.trim()
        this.assistantBuffer = ''
        if (text) this.pushMessage('assistant', text.slice(0, 1200))
        this.setState({ phase: 'ready' })
        break
      }
      case 'gemini.tool_call':
        void this.handleFunctionCall(event)
        break
      case 'error': {
        const code = typeof event.code === 'string' ? event.code : ''
        if (code === 'connection_closed') {
          this.setState({ phase: 'error', error: 'Voice connection closed - tap the orb to reconnect.' })
        }
        break
      }
      default:
        break
    }
  }

  private pushMessage(role: 'user' | 'assistant', text: string): void {
    const message: VoiceMessage = {
      id: `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      role,
      kind: role,
      text,
      time: Date.now(),
    }
    this.setState({ messages: [...this.state.messages, message] })
  }

  private async handleFunctionCall(event: Record<string, unknown>): Promise<void> {
    const calls = (event.calls as { name?: unknown; args?: unknown }[] | undefined) ?? []
    const clean = calls.filter((c) => typeof c.name === 'string' && c.name.length > 0)
    if (clean.length === 0) return

    const responses: { name: string; response: Record<string, unknown> }[] = []
    this.setState({ phase: 'thinking' })

    for (const call of clean) {
      const name = call.name as string
      const args = (call.args as Record<string, unknown>) ?? {}

      const invocation: VoiceToolInvocation = {
        id: `tc-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        name,
        args,
        status: 'executing',
        time: Date.now(),
      }
      this.setState({ toolInvocations: [...this.state.toolInvocations, invocation] })

      const result = await executeTool(this.tools, name, args)
      if (result.source === 'web' && result.status === 'ok') {
        this.setState({ webUsed: true })
      }
      if (name === 'ui_navigate') {
        publishVoiceCommand('voice:navigate', args)
      }

      this.setState({
        toolInvocations: this.state.toolInvocations.map((inv) =>
          inv.id === invocation.id
            ? { ...inv, status: result.status === 'ok' ? 'ok' : 'error', feedback: result.feedback }
            : inv,
        ),
      })

      responses.push({ name, response: result as unknown as Record<string, unknown> })
    }

    this.client.sendToolResponse(responses)
  }

  private setState(patch: Partial<VoiceSessionState>): void {
    this.state = { ...this.state, ...patch }
    this.onState(this.state)
  }
}