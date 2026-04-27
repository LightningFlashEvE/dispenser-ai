/**
 * PCM AudioWorklet Processor
 *
 * 在独立 AudioWorklet 线程里把麦克风 Float32 样本转换为 Int16 PCM，
 * 每 320 帧（20 ms @ 16kHz）打包一次，通过 MessagePort 传回主线程。
 *
 * 支持暂停/恢复控制：
 *   'start' → 开始输出数据
 *   'stop'  → 暂停输出（但线程保持存活）
 */

const FRAME_SAMPLES = 320 // 20 ms × 16000 Hz

class PcmProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this._buf = new Float32Array(FRAME_SAMPLES)
    this._offset = 0
    this._paused = true
    this.port.onmessage = (evt) => {
      if (evt.data === 'stop') {
        this._paused = true
      } else if (evt.data === 'start') {
        this._paused = false
        this._offset = 0
        this._buf.fill(0)
      }
    }
  }

  process(inputs) {
    if (this._paused) return true
    const ch = inputs[0]?.[0]
    if (!ch) return true

    let i = 0
    while (i < ch.length) {
      const space = FRAME_SAMPLES - this._offset
      const take = Math.min(space, ch.length - i)
      this._buf.set(ch.subarray(i, i + take), this._offset)
      this._offset += take
      i += take
      if (this._offset >= FRAME_SAMPLES) {
        this._flush()
      }
    }
    return true
  }

  _flush() {
    const int16 = new Int16Array(FRAME_SAMPLES)
    for (let j = 0; j < FRAME_SAMPLES; j++) {
      const s = Math.max(-1, Math.min(1, this._buf[j]))
      int16[j] = Math.round(s < 0 ? s * 32768 : s * 32767)
    }
    this.port.postMessage(int16.buffer, [int16.buffer])
    this._offset = 0
    this._buf.fill(0)
  }
}

registerProcessor('pcm-processor', PcmProcessor)
