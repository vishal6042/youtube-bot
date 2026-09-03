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

/* Each playlist gets its own identity colour, matching its cover art. The name
   is always in the chip too, so colour is never the only signal. */
export const seriesChip = (series) => `chip-pl pl-${series}`;

export const STATE_CHIP = {
  uploaded: ["chip-uploaded", "✅ UPLOADED"],
  ready: ["chip-ready", "⏳ READY"],
  rendered: ["chip-rendered", "🎬 RENDERED"],
  missing: ["chip-missing", "⬜ NOT MADE"],
  discarded: ["chip-missing", "🗑 DISCARDED"],
};

// The orchestrator's sub-agents, in pipeline order. Keys match the
// ::stage:: markers emitted by dashboard/worker.py.
export const AGENTS = [
  { key: "video", icon: "🎬", label: "VIDEO CREATION" },
  { key: "music", icon: "🎵", label: "MUSIC GEN" },
  { key: "mixing", icon: "🎚️", label: "MIX & SYNC" },
  { key: "subtitle", icon: "📝", label: "TITLES & DESC" },
  { key: "exporting", icon: "📦", label: "EXPORT" },
  { key: "thumbnail", icon: "🖼️", label: "THUMBNAIL" },
];

export const AGENT_TEXT = {
  idle: "STANDING BY",
  queued: "QUEUED",
  starting: "SPOOLING UP",
  video: "CREATING VIDEO",
  music: "GENERATING MUSIC",
  mixing: "MIXING & SYNCING",
  subtitle: "WRITING TITLES & CAPTIONS",
  exporting: "EXPORTING",
  thumbnail: "BUILDING THUMBNAIL",
  exported: "TOPIC COMPLETE",
  error: "JOB FAILED",
};
