export type StatusTone = 'ok' | 'warn' | 'danger' | 'info' | 'offline'

export interface StatusDescriptor {
  label: string
  tone: StatusTone
}

export function taskStatusDescriptor(status?: string | null): StatusDescriptor {
  const value = status?.toUpperCase() ?? ''
  if (value.includes('FAILED') || value.includes('ERROR')) return { label: status ?? '异常', tone: 'danger' }
  if (value.includes('COMPLETED')) return { label: status ?? '完成', tone: 'ok' }
  if (value.includes('CANCEL')) return { label: status ?? '已取消', tone: 'offline' }
  if (value.includes('CONFIRM') || value.includes('PENDING') || value.includes('ASK')) return { label: status ?? '待确认', tone: 'warn' }
  if (value.includes('EXECUT') || value.includes('RUN') || value.includes('PROCESS')) return { label: status ?? '运行中', tone: 'info' }
  return { label: status || '待机', tone: 'offline' }
}

export function connectionStatusDescriptor(connected: boolean, error = false, loading = false): StatusDescriptor {
  if (error) return { label: '异常', tone: 'danger' }
  if (loading) return { label: '连接中', tone: 'info' }
  return connected ? { label: '在线', tone: 'ok' } : { label: '离线', tone: 'offline' }
}

export function balanceStatusDescriptor(valueMg: number | null, stable: boolean, overLimit: boolean): StatusDescriptor {
  if (overLimit) return { label: '异常 / 超限', tone: 'danger' }
  if (valueMg === null) return { label: '等待数据', tone: 'offline' }
  return stable ? { label: '稳定', tone: 'ok' } : { label: '波动', tone: 'warn' }
}

export function balanceSourceStatusDescriptor(source: 'REALTIME' | 'SNAPSHOT' | 'STALE' | 'NO_DATA', stable: boolean, overLimit: boolean): StatusDescriptor {
  if (overLimit) return { label: '异常 / 超限', tone: 'danger' }
  if (source === 'NO_DATA') return { label: '等待数据', tone: 'offline' }
  if (source === 'STALE') return { label: '实时流中断', tone: 'warn' }
  if (source === 'SNAPSHOT') return { label: '快照数据', tone: 'info' }
  return stable ? { label: '稳定', tone: 'ok' } : { label: '波动', tone: 'warn' }
}

export function resourceTone(percent: number): StatusTone {
  if (percent >= 85) return 'danger'
  if (percent >= 70) return 'warn'
  return 'info'
}

export function resourceBarClass(percent: number): string {
  if (percent >= 85) return 'bg-red-400'
  if (percent >= 70) return 'bg-amber-400'
  return 'bg-cyan-400'
}
