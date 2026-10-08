/* Helpers shared by the live-run card and the Jobs screen. */

const parse = (iso) => (iso ? new Date(String(iso).replace(" ", "T")).getTime() : NaN);

/* Seconds between two ISO stamps; `to` defaults to now. null when unknown. */
export function secsBetween(from, to) {
  const a = parse(from);
  const b = to ? parse(to) : Date.now();
  return isNaN(a) || isNaN(b) ? null : Math.max(0, (b - a) / 1000);
}

/* The worker talks to the server through ::marker:: lines. They are protocol,
   not log output, so they are dropped; a failure marker carries the only copy
   of the error, so that one is rewritten into a readable line instead. */
export function cleanLog(lines) {
  const out = [];
  for (const raw of lines || []) {
    const failed = /^::failed::([^:]+)::(.*)$/.exec(raw);
    if (failed) { out.push(`Failed ${failed[1]}: ${failed[2]}`); continue; }
    if (/^\s*::\w+::/.test(raw)) continue;
    const line = raw.replace(/::agent::\w+::\w+/g, "").trimEnd();
    if (line) out.push(line);
  }
  return out;
}

/* Older job records predate the steps timeline, so rebuild it from their log. */
export function stepsOf(job) {
  if (job.steps?.length) return job.steps;
  const out = [];
  let topic = null;
  // Markers may share a line with other output, so match rather than split.
  const re = /::agent::(\w+)::(active|done|failed)\b/;
  for (const line of job.log || []) {
    if (line.startsWith("::topic::")) topic = line.split("::topic::")[1].trim();
    const m = re.exec(line);
    if (!m) continue;
    const [, name, state] = m;
    if (state === "active") out.push({ agent: name, topic, state: "active", secs: null });
    else {
      const open = [...out].reverse().find((s) => s.agent === name && s.state === "active");
      if (open) open.state = state;
      else out.push({ agent: name, topic, state, secs: null });
    }
  }
  return out;
}

export const keysOf = (job) =>
  job.keys?.length ? job.keys : Object.keys(job.results || {});

export const failedKeys = (job) =>
  Object.entries(job.results || {}).filter(([, r]) => r.status === "failed").map(([k]) => k);

const REASONS = [
  [/broadcast|operands|shape/i, "The animation crashed while drawing"],
  [/timed? ?out/i, "A step took too long and was stopped"],
  [/ffmpeg/i, "The video could not be encoded"],
  [/HTTP|URLError|Connection|getaddrinfo|SSL|socket/i, "The source data could not be downloaded"],
  [/FileNotFound|No such file/i, "A file the render needed was missing"],
  [/Permission|WinError 32|being used by another/i, "A file was locked by another program"],
  [/MemoryError|out of memory/i, "The machine ran out of memory"],
  [/charmap|codec can't|Unicode/i, "Some text could not be written (character encoding)"],
  [/KeyError|column|empty|no data|ValueError/i, "The source data was not in the expected shape"],
];

/* Plain-language headline for a raw error; the raw text stays one click away. */
export function explain(error) {
  if (!error) return "The render stopped without reporting why";
  const hit = REASONS.find(([re]) => re.test(error));
  return hit ? hit[1] : "The render stopped with an error";
}

export const stepSecs = (secs) =>
  secs == null ? "" : secs < 1 ? "under 1s"
    : secs >= 60 ? `${Math.floor(secs / 60)}m ${String(Math.round(secs % 60)).padStart(2, "0")}s`
    : `${Math.round(secs)}s`;
