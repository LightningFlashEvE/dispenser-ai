import { defineStore } from 'pinia'
import { ref } from 'vue'

export type DialogState =
  | 'IDLE'
  | 'LISTENING'
  | 'PROCESSING'
  | 'ASKING'
  | 'EXECUTING'
  | 'FEEDBACK'
  | 'ERROR'

export interface Message {
  role: 'user' | 'assistant'
  text: string
  timestamp: string
}

export interface CommandResult {
  command_id: string
  status: 'completed' | 'failed' | 'cancelled' | 'partial'
  result: unknown
  error: { code: string; message: string } | null
  completed_at: string
}

export const useVoiceStore = defineStore('voice', () => {
  const dialogState = ref<DialogState>('IDLE')
  const realtimeCaption = ref('')
  const transcript = ref<Message[]>([])
  const latestQuestion = ref<string | null>(null)
  const latestCommandResult = ref<CommandResult | null>(null)
  const isConnected = ref(false)
  const isTtsSpeaking = ref(false)

  function setState(s: DialogState) {
    dialogState.value = s
  }

  function setCaption(text: string) {
    realtimeCaption.value = text
  }

  function addMessage(msg: Message) {
    transcript.value.push(msg)
  }

  function setQuestion(q: string | null) {
    latestQuestion.value = q
  }

  function setCommandResult(r: CommandResult | null) {
    latestCommandResult.value = r
  }

  function setConnected(v: boolean) {
    isConnected.value = v
  }

  function setTtsSpeaking(v: boolean) {
    isTtsSpeaking.value = v
  }

  function reset() {
    dialogState.value = 'IDLE'
    realtimeCaption.value = ''
    latestQuestion.value = null
    latestCommandResult.value = null
    isTtsSpeaking.value = false
  }

  return {
    dialogState,
    realtimeCaption,
    transcript,
    latestQuestion,
    latestCommandResult,
    isConnected,
    isTtsSpeaking,
    setState,
    setCaption,
    addMessage,
    setQuestion,
    setCommandResult,
    setConnected,
    setTtsSpeaking,
    reset,
  }
})
