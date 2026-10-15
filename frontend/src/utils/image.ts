// 图片本地压缩链 —— 平移 web-legacy/app.js prepareImage/canvasDataUrl

export interface PreparedImage {
  original: string // dataURL
  thumbnail: string // dataURL
  width: number
  height: number
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(new Error('这张图片无法读取'))
    reader.readAsDataURL(file)
  })
}

function canvasDataUrl(source: ImageBitmap, maxEdge: number, quality: number): string {
  const scale = Math.min(1, maxEdge / Math.max(source.width, source.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(source.width * scale))
  canvas.height = Math.max(1, Math.round(source.height * scale))
  const context = canvas.getContext('2d')!
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, canvas.width, canvas.height)
  context.drawImage(source, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', quality)
}

/** 缩略 360px q0.82；>8MB 原图压到 2560px q0.9；单张上限 12MB */
export async function prepareImage(file: File): Promise<PreparedImage> {
  if (!file.type.startsWith('image/')) {
    throw new Error('请选择图片文件')
  }
  if (file.size > 12_000_000) {
    throw new Error('单张图片请小于 12 MB')
  }
  const bitmap = await createImageBitmap(file)
  const width = bitmap.width
  const height = bitmap.height
  const thumbnail = canvasDataUrl(bitmap, 360, 0.82)
  const original = file.size > 8_000_000 ? canvasDataUrl(bitmap, 2560, 0.9) : await readFileAsDataUrl(file)
  bitmap.close?.()
  return { original, thumbnail, width, height }
}

/** 头像压缩：256px JPEG 0.85（平移 resizeAvatar） */
export async function resizeAvatar(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file)
  const dataUrl = canvasDataUrl(bitmap, 256, 0.85)
  bitmap.close?.()
  return dataUrl
}
