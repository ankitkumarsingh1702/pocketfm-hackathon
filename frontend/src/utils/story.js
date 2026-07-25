/**
 * Story-text domain helpers.
 *
 * The episode textarea is a single string with scenes separated by a delimiter
 * (default `---`). These helpers turn that raw text into structured data the
 * controllers can reason about — without any of them knowing about React.
 */

import { SCENE_DELIMITER } from '../config/constants'

/** Split raw episode text into trimmed, non-empty scene strings. */
export function splitScenes(text, delimiter = SCENE_DELIMITER) {
  return String(text || '')
    .split(delimiter)
    .map((scene) => scene.trim())
    .filter(Boolean)
}

/** Number of scenes in the episode text. */
export function countScenes(text, delimiter = SCENE_DELIMITER) {
  return splitScenes(text, delimiter).length
}

/** Rough word count for the episode text. */
export function countWords(text) {
  const trimmed = String(text || '').trim()
  return trimmed ? trimmed.split(/\s+/).length : 0
}

/** True when the episode text has no usable content. */
export function isBlank(text) {
  return String(text || '').trim().length === 0
}

/**
 * The last scene of the episode — used as the "weak ending" the Cliffhanger
 * Optimizer rewrites. Falls back to the whole text when there are no delimiters.
 */
export function lastScene(text, delimiter = SCENE_DELIMITER) {
  const scenes = splitScenes(text, delimiter)
  return scenes.length ? scenes[scenes.length - 1] : String(text || '').trim()
}
