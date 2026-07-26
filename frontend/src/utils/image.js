/**
 * Client-side image helpers for the Audience Simulator post composer.
 *
 * The posted image is sent to every reaction agent, so we downscale it in the
 * browser before upload — smaller payloads keep the request light and every
 * per-agent vision call fast and cheap, at no visible quality cost for a feed
 * image.
 */

const readAsDataUrl = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(new Error('Could not read the image file.'))
    reader.readAsDataURL(file)
  })

const loadImage = (src) =>
  new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('Could not decode the image.'))
    img.src = src
  })

/**
 * Read an image File and downscale it to fit within `maxDim` px on its longest
 * side, re-encoding as JPEG.
 *
 * @param {File} file
 * @param {number} [maxDim=1024]
 * @param {number} [quality=0.85]
 * @returns {Promise<{dataUrl:string, base64:string, mime:string, name:string}>}
 */
export async function fileToDownscaledImage(file, maxDim = 1024, quality = 0.85) {
  const original = await readAsDataUrl(file)
  const img = await loadImage(original)

  const scale = Math.min(1, maxDim / Math.max(img.width, img.height))
  const width = Math.max(1, Math.round(img.width * scale))
  const height = Math.max(1, Math.round(img.height * scale))

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas is not available in this browser.')
  ctx.drawImage(img, 0, 0, width, height)

  const mime = 'image/jpeg'
  const dataUrl = canvas.toDataURL(mime, quality)
  const base64 = dataUrl.split(',')[1] || ''
  return { dataUrl, base64, mime, name: file.name || 'image' }
}
