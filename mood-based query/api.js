/**
 * Single place that knows how to reach the backend.
 *
 * Components import these functions and never see a URL, a fetch, or an env
 * var. That is the point: the base URL is configured in exactly one spot, so
 * whatever your build uses — import.meta.env, a runtime config object, a
 * hardcoded dev value, a proxy in the dev server — only this file changes.
 *
 * Set BASE to match your project. If you already have an http/axios client
 * with interceptors, replace the `request` body with a call to it and leave
 * the exported functions alone.
 */

const BASE = "";

async function request(path, { method = "GET", body } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    throw new Error(`${method} ${path} failed: ${res.status}`);
  }
  return res.json();
}

export const getStarters = () => request("/starters");
export const getSliders = () => request("/sliders");
export const getProfiles = () => request("/profiles");

export const search = (text, profileId) =>
  request("/search", { method: "POST", body: { text, profile_id: profileId } });

export const answerClarify = (queryId, optionId) =>
  request("/clarify", { method: "POST", body: { query_id: queryId, option_id: optionId } });

export const refineShelf = (queryId, shelfId, currentAxes, sliderDeltas) =>
  request("/refine", {
    method: "POST",
    body: {
      query_id: queryId,
      shelf_id: shelfId,
      current_axes: currentAxes,
      slider_deltas: sliderDeltas,
    },
  });

export const getEpisodes = (seriesId, start = 1, limit = 12) =>
  request(`/episodes/${encodeURIComponent(seriesId)}?start=${start}&limit=${limit}`);

export const runBaseline = (text, k = 3) =>
  request("/baseline", { method: "POST", body: { text, k } });

export const getDebug = (queryId) => request(`/debug/${queryId}`);
