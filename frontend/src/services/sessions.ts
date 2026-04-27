import axios from 'axios'

const http = axios.create({ baseURL: '/', timeout: 15000 })

export interface SessionListItem {
  session_id: string
  title: string
  message_count: number
  round_count: number
  created_at: string
  updated_at: string
}

export interface SessionDetail {
  session_id: string
  title: string
  messages: Array<{ role: string; content: string }>
  round_count: number
  task_id: string | null
  created_at: string
  updated_at: string
}

export interface SessionMessage {
  role: 'user' | 'assistant'
  content: string
}

export const sessionApi = {
  list: (p?: { skip?: number; limit?: number }) =>
    http.get<SessionListItem[]>('/api/dialog-sessions', { params: p }).then((r) => r.data),

  get: (sessionId: string) =>
    http.get<SessionDetail>(`/api/dialog-sessions/${sessionId}`).then((r) => r.data),

  create: () =>
    http.post<{ session_id: string }>('/api/dialog-sessions').then((r) => r.data),

  update: (sessionId: string, messages: SessionMessage[], roundCount?: number) =>
    http.patch(`/api/dialog-sessions/${sessionId}`, {
      messages,
      round_count: roundCount,
    }),

  delete: (sessionId: string) =>
    http.delete(`/api/dialog-sessions/${sessionId}`),
}
