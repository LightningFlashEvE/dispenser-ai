import { sendAudioChunk, sendJson } from './websocket'

let mediaStream: MediaStream | null = null
let audioContext: AudioContext | null = null
let processor: ScriptProcessorNode | null = null

export async function startRecording(): Promise<void> {
  mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
  audioContext = new AudioContext({ sampleRate: 16000 })
  const source = audioContext.createMediaStreamSource(mediaStream)
  processor = audioContext.createScriptProcessor(4096, 1, 1)

  processor.onaudioprocess = (e: AudioProcessingEvent) => {
    const float32 = e.inputBuffer.getChannelData(0)
    const int16 = float32ToInt16(float32)
    sendAudioChunk(int16.buffer as ArrayBuffer)
  }

  source.connect(processor)
  processor.connect(audioContext.destination)
}

export function stopRecording(): void {
  processor?.disconnect()
  audioContext?.close()
  mediaStream?.getTracks().forEach(t => t.stop())
  processor = null
  audioContext = null
  mediaStream = null
  sendJson({ type: 'audio_end' })
}

export function cancelDialog(): void {
  stopRecording()
  sendJson({ type: 'cancel' })
}

function float32ToInt16(buffer: Float32Array): Int16Array {
  const out = new Int16Array(buffer.length)
  for (let i = 0; i < buffer.length; i++) {
    const s = Math.max(-1, Math.min(1, buffer[i]))
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return out
}
