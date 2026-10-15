// 富文本/备注的 HTML 处理 —— 忠实平移 web-legacy/app.js 的实现
// Vue 模板里用 v-html 渲染 memo 内容时仍然依赖这里的白名单消毒。

export function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

/** 纯文本备注 → HTML（URL 自动成链接 + 复制按钮） */
export function renderNote(value: string): string {
  const text = String(value || '')
  if (!text.trim()) return ''
  const pattern = /https?:\/\/[^\s<>"']+/gi
  let html = ''
  let lastIndex = 0
  for (const match of text.matchAll(pattern)) {
    const rawUrl = match[0].replace(/[),.;，。；、]+$/u, '')
    html += escapeHtml(text.slice(lastIndex, match.index)).replaceAll('\n', '<br>')
    const href = escapeHtml(rawUrl)
    html += `<span class="note-link">
      <a href="${href}" target="_blank" rel="noopener noreferrer">${href}</a>
      <button type="button" class="copy-link" data-action="copy-link" data-url="${href}">复制</button>
    </span>`
    lastIndex = match.index + rawUrl.length
  }
  html += escapeHtml(text.slice(lastIndex)).replaceAll('\n', '<br>')
  return html
}

export function looksLikeRichHtml(value: string): boolean {
  return /<\s*(p|br|strong|b|ul|ol|li|h3|div|span)\b/i.test(String(value || ''))
}

/** 白名单消毒：P/BR/STRONG/B/UL/OL/LI/H3/DIV/SPAN，H1/H2→H3，DIV→P */
export function sanitizeRichHtml(html: string): string {
  const template = document.createElement('template')
  template.innerHTML = String(html || '')
  const allowed = new Set(['P', 'BR', 'STRONG', 'B', 'UL', 'OL', 'LI', 'H3', 'DIV', 'SPAN'])
  const clean = (node: Node): DocumentFragment => {
    const fragment = document.createDocumentFragment()
    ;[...node.childNodes].forEach((child) => {
      if (child.nodeType === Node.TEXT_NODE) {
        fragment.append(document.createTextNode(child.textContent ?? ''))
        return
      }
      if (child.nodeType !== Node.ELEMENT_NODE) return
      let tag = (child as Element).tagName
      if (tag === 'H1' || tag === 'H2') tag = 'H3'
      if (tag === 'DIV') tag = 'P'
      if (!allowed.has(tag) && tag !== 'P' && tag !== 'H3') {
        fragment.append(clean(child))
        return
      }
      if (tag === 'SPAN') {
        fragment.append(clean(child))
        return
      }
      const element = document.createElement(tag.toLowerCase())
      if ((child as Element).classList.contains('note-lg')) element.classList.add('note-lg')
      if ((child as Element).classList.contains('note-title')) element.classList.add('note-title')
      if (tag !== 'BR') element.append(clean(child))
      fragment.append(element)
    })
    return fragment
  }
  const holder = document.createElement('div')
  holder.append(clean(template.content))
  return holder.innerHTML.trim()
}

/** 富文本 → 纯文本摘要 */
export function plainNoteText(content: string): string {
  const text = String(content || '')
  if (!text) return ''
  if (!looksLikeRichHtml(text)) return text.replace(/\s+/g, ' ').trim()
  const holder = document.createElement('div')
  holder.innerHTML = sanitizeRichHtml(text)
  return (holder.textContent ?? '').replace(/\s+/g, ' ').trim()
}

/** memo 内容渲染入口：富文本走白名单，纯文本走链接化 */
export function renderMemoHtml(content: string): string {
  if (!content) return ''
  if (!looksLikeRichHtml(content)) return renderNote(content)
  return sanitizeRichHtml(content)
}

/** 把文本里的 【...】（1-24 字）包成 span.note-slot（编辑器/模板用） */
export function markNoteSlots(root: ParentNode) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  while (walker.nextNode()) nodes.push(walker.currentNode as Text)
  nodes.forEach((node) => {
    const parts = (node.textContent ?? '').split(/(【[^】]{1,24}】)/)
    if (parts.length === 1) return
    const fragment = document.createDocumentFragment()
    parts.forEach((part) => {
      if (/^【[^】]{1,24}】$/.test(part)) {
        const slot = document.createElement('span')
        slot.className = 'note-slot'
        slot.textContent = part
        fragment.append(slot)
      } else if (part) {
        fragment.append(document.createTextNode(part))
      }
    })
    node.parentNode?.replaceChild(fragment, node)
  })
}

export function safeHttpUrl(value: string): string {
  const raw = String(value || '').trim()
  if (!raw) return ''
  try {
    const parsed = new URL(raw)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return ''
    return parsed.href
  } catch {
    return ''
  }
}

export function splitTags(value: string): string[] {
  return String(value || '')
    .split(/[,，\s]+/)
    .map((tag) => tag.trim())
    .filter(Boolean)
}

export async function copyTextToClipboard(url: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(url)
    return true
  } catch {
    try {
      const field = document.createElement('textarea')
      field.value = url
      document.body.append(field)
      field.select()
      document.execCommand('copy')
      field.remove()
      return true
    } catch {
      return false
    }
  }
}
