/**
 * websocket.ts  —  统一 WebSocket 连接 + 消息模型
 */

export type SessionState =
  | 'idle' | 'listening' | 'recognizing' | 'thinking'
  | 'speaking' | 'awaiting_confirmation' | 'interrupted'
  | 'IDLE' | 'LISTENING' | 'PROCESSING' | 'ASKING' | 'EXECUTING' | 'FEEDBACK' | 'ERROR'

export interface PendingPayload {
  intent_id: string | null
  intent_type: string | null
  params: Record<string, unknown>
  reagent_hint: unknown
  drug: { reagent_code: string | null; reagent_name_cn: string | null; station_id: string | null } | null
  expires_at: string
}

export interface SlotFillingPayload { missing_slots: string[]; question: string }
export interface CommandResultPayload { command_id: string; status: string; message?: string }
export interface DraftPayload {
  draft_id: string
  session_id: string
  task_type: 'WEIGHING' | 'MIXING' | 'DISPENSING'
  status: string
  complete: boolean
  missing_slots: string[]
  ready_for_review: boolean
  current_draft: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface Correction {
  from: string
  to: string
  type: string
  confidence: number
  reason: string
}

export interface Suggestion {
  text: string
  candidate: string
  confidence: number
  reason: string
}

export type InboundMsg =
  | { type: 'connected'; client_id: string; timestamp: string }
  | { type: 'state.update'; state: SessionState }
  | { type: 'asr.partial'; text: string }
  | { type: 'asr.final'; text: string; duration_ms?: number; raw_text?: string; normalized_text?: string; corrections?: Correction[]; suggestions?: Suggestion[]; needs_confirmation?: boolean }
  | { type: 'chat.delta'; text: string; seq: number }
  | { type: 'chat.done'; text: string }
  | { type: 'tts.chunk'; data: string; sample_rate: number; format: string; seq: number; text?: string }
  | { type: 'tts.done' }
  | { type: 'tts_end' }
  | { type: 'pending_intent'; data: PendingPayload }
  | { type: 'draft_update'; data: DraftPayload }
  | { type: 'pending_cleared' }
  | { type: 'slot_filling'; data: SlotFillingPayload }
  | { type: 'question'; text: string }
  | { type: 'dialog_reply'; text: string }
  | { type: 'user_message'; text: string; timestamp: string }
  | { type: 'command_sent'; command_id: string }
  | { type: 'command_result'; data: CommandResultPayload }
  | { type: 'balance_reading'; value_mg: number; stable: boolean; timestamp: string }
  | { type: 'balance_over_limit'; value_mg: number }
  | { type: 'error'; code: string; message: string }
  | { type: 'ping'; ts: string }
  | { type: 'state_change'; state: string }
  | { type: 'stt_final'; text: string; duration_ms?: number }

export type OutboundMsg =
  | { type: 'chat.user_text'; text: string; timestamp: string }
  | { type: 'audio.commit' }
  | { type: 'barge_in' }
  | { type: 'confirm' }
  | { type: 'cancel_pending' }
  | { type: 'cancel' }

export type MsgHandler = (msg: InboundMsg) => void
export type ConnectionHandler = (connected: boolean) => void

export class VoiceWebSocket {
  private ws: WebSocket | null = null
  private _msgHandler: MsgHandler | null = null
  private _connHandler: ConnectionHandler | null = null
  private _url = ''
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private _shouldReconnect = false
  private _reconnectDelay = 2000

  connect(url: string, onMsg: MsgHandler, onConn?: ConnectionHandler): void {
    this._url = url
    this._msgHandler = onMsg
    this._connHandler = onConn ?? null
    this._shouldReconnect = true
    this._doConnect()
  }

  reconnectWithSession(sessionId: string): void {
    const urlObj = new URL(this._url, location.href)
    urlObj.searchParams.set('session_id', sessionId)
    this.disconnect()
    this._shouldReconnect = true
    this._url = urlObj.toString()
    this._doConnect()
  }

  private _doConnect(): void {
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) return
    this.ws = new WebSocket(this._url)
    this.ws.binaryType = 'arraybuffer'

    this.ws.onopen = () => {
      this._connHandler?.(true)
      this._reconnectDelay = 2000
    }
    this.ws.onclose = () => {
      this._connHandler?.(false)
      if (this._shouldReconnect) {
        this._reconnectTimer = setTimeout(() => {
          this._reconnectDelay = Math.min(this._reconnectDelay * 1.5, 15000)
          this._doConnect()
        }, this._reconnectDelay)
      }
    }
    this.ws.onerror = () => { /* onclose 处理重连 */ }
    this.ws.onmessage = (evt: MessageEvent) => {
      if (typeof evt.data !== 'string') return
      let msg: InboundMsg
      try { msg = JSON.parse(evt.data) as InboundMsg } catch { return }
      this._msgHandler?.(msg)
    }
  }

  sendJson(msg: OutboundMsg): boolean {
    if (!this._isOpen()) {
      console.warn('[ws] drop outbound msg, socket not open:', msg)
      return false
    }

    try {
      this.ws!.send(JSON.stringify(msg))
      return true
    } catch (e) {
      console.warn('[ws] send failed:', e, msg)
      return false
    }
  }

  sendAudioFrame(frame: ArrayBuffer): void {
    if (!this._isOpen()) return
    this.ws!.send(frame)
  }

  commitAudio(): boolean { return this.sendJson({ type: 'audio.commit' }) }
  sendUserText(text: string): boolean {
    return this.sendJson({ type: 'chat.user_text', text, timestamp: new Date().toISOString() })
  }
  bargeIn(): boolean { return this.sendJson({ type: 'barge_in' }) }
  confirm(): boolean { return this.sendJson({ type: 'confirm' }) }
  cancelPending(): boolean { return this.sendJson({ type: 'cancel_pending' }) }
  cancelTask(): boolean { return this.sendJson({ type: 'cancel' }) }

  disconnect(): void {
    this._shouldReconnect = false
    if (this._reconnectTimer) clearTimeout(this._reconnectTimer)
    this.ws?.close()
    this.ws = null
  }

  get isConnected(): boolean { return this._isOpen() }
  private _isOpen(): boolean { return this.ws !== null && this.ws.readyState === WebSocket.OPEN }
}
