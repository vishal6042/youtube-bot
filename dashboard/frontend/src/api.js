export async function api(path, body) {
  const opts = body
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    : {};
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      msg = (await res.json()).detail || msg;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(msg);
  }
  return res.json();
}

/* Each playlist gets its own identity colour. The name is always shown beside
   it, so colour is never the only signal. */
export const PLAYLIST_COLORS = {
  world_in_data: "#38e1ff",
  india_in_data: "#ff9d5c",
  money: "#f0c14b",
  ai_trends: "#ff4fd8",
  sports: "#3ddc97",
  ml_concept: "#a78bfa",
  charts_lie: "#ff7a90",
  country_vs_country: "#6f9bff",
};

// The render pipeline's steps, in order. Keys match the ::agent:: markers
// emitted by dashboard/worker.py; `hint` says what each step is waiting on.
export const STEPS = [
  { key: "video", label: "Video", doing: "Drawing the video", hint: "fetch, transform, render" },
  { key: "music", label: "Music", doing: "Picking music", hint: "track for the topic's mood" },
  { key: "subtitle", label: "Titles", doing: "Writing title and description", hint: "title and description" },
  { key: "mixing", label: "Mix", doing: "Mixing sound", hint: "needs the video" },
  { key: "exporting", label: "Export", doing: "Exporting", hint: "after the mix" },
  { key: "thumbnail", label: "Thumbnail", doing: "Making the thumbnail", hint: "after export" },
];
