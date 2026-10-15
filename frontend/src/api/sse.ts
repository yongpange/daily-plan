// SSE 流式响应通用封装（预留：后续大模型对话 / 生图进度使用，当前不接业务）
// 后端帧格式：data: <json>\n\n（无 event/id 字段）

export interface StreamHandle {
  /** 中断流 */
  abort: () => void
  /** 流是否正常结束（done 帧或连接关闭） */
  finished: Promise<boolean>
}

/**
 * POST 一个流式端点，逐帧回调解析后的 JSON 对象。
 * onEvent 返回 false 可提前终止读取。
 */
export function postStream<T>(
  url: string,
  body: unknown,
  onEvent: (event: T) => boolean | void,
  init?: { apiKey?: string },
): StreamHandle {
  const controller = new AbortController()
  const finished = (async (): Promise<boolean> => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (init?.apiKey) headers['X-API-Key'] = init.apiKey
    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    if (!response.ok || !response.body) return false

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) return true
      buffer += decoder.decode(value, { stream: true })
      // 帧以空行分隔
      const frames = buffer.split('\n\n')
      buffer = frames.pop() ?? ''
      for (const frame of frames) {
        const dataLine = frame
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart())
          .join('\n')
        if (!dataLine) continue
        let event: T
        try {
          event = JSON.parse(dataLine) as T
        } catch {
          continue
        }
        if (onEvent(event) === false) {
          controller.abort()
          return true
        }
      }
    }
  })()
  return { abort: () => controller.abort(), finished }
}
