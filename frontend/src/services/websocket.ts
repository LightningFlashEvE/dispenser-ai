import { useVoiceStore, type DialogState } from '@/stores/voice'
import { useVisionStore } from '@/stores/vision'

type WsMessage =
  | { type: 'stt_partial'; text: string }
  | { type: 'stt_final'; text: string }
  | { type: 'state_change'; state: string }
  | { type: 'question'; text: string }
  | { type: 'tts_audio'; audio_b64: string }
  | { type: 'vision_result'; stations: unknown[] }
  | { type: 'balance_reading'; mass_mg: number; stable: boolean; timestamp: string }
  | { type: 'command_sent'; command_id: string }
  | { type: 'command_result'; data: unknown }
  | { type: 'error'; code: string; message: string }

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

export function connectWebSocket(url: string = `ws://${location.host}/ws/voice`) {
  const voiceStore = useVoiceStore()
  const visionStore = useVisionStore()

  if (ws && ws.readyState === WebSocket.OPEN) return

  ws = new WebSocket(url)

  ws.onopen = () => {
    voiceStore.setConnected(true)
    if (reconnectTimer) clearTimeout(reconnectTimer)
  }

  ws.onclose = () => {
    voiceStore.setConnected(false)
    reconnectTimer = setTimeout(() => connectWebSocket(url), 3000)
  }

  ws.onerror = () => {
    ws?.close()
  }

  ws.onmessage = (event: MessageEvent) => {
    let msg: WsMessage
    try {
      msg = JSON.parse(event.data as string) as WsMessage
    } catch {
      return
    }

    switch (msg.type) {
      case 'stt_partial':
        voiceStore.setCaption(msg.text)
        break
      case 'stt_final':
        voiceStore.setCaption(msg.text)
        voiceStore.addMessage({ role: 'user', text: msg.text, timestamp: new Date().toISOString() })
        break
      case 'state_change':
        voiceStore.setState(msg.state as DialogState)
        break
      case 'question':
        voiceStore.setQuestion(msg.text)
        voiceStore.addMessage({ role: 'assistant', text: msg.text, timestamp: new Date().toISOString() })
        break
      case 'vision_result':
        visionStore.updateStations(msg.stations as Parameters<typeof visionStore.updateStations>[0])
        break
      case 'balance_reading':
        visionStore.updateBalance({ mass_mg: msg.mass_mg, stable: msg.stable, timestamp: msg.timestamp })
        break
      case 'command_result':
        voiceStore.setCommandResult(msg.data as Parameters<typeof voiceStore.setCommandResult>[0])
        break
    }
  }
}

export function sendAudioChunk(chunk: ArrayBuffer) {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(chunk)
  }
}

export function sendJson(payload: Record<string, unknown>) {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload))
  }
}

export function disconnectWebSocket() {
  if (reconnectTimer) clearTimeout(reconnectTimer)
  ws?.close()
  ws = null
}
