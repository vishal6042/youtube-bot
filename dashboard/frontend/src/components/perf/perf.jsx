import { useEffect, useState } from "react";
import { api } from "../../api.js";
import { Chip, fmtNum, fmtWhen } from "../../ui.jsx";

/* Channel performance from /api/perf: stored YouTube snapshots, no quota. */
export function usePerf(deps = []) {
  const [perf, setPerf] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let alive = true;
    api("/api/perf")
      .then((r) => alive && (setPerf(r), setError(null)))
      .catch((e) => alive && setError(e.message));
    return () => { alive = false; };
  }, deps);  // eslint-disable-line react-hooks/exhaustive-deps
  return { perf, error };
}

/* "5:07", "0:26" */
export const fmtLen = (secs) => {
  if (secs == null) return "";
  const s = Math.round(secs);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

const SHORT_C = "#f5a524";
const VIDEO_C = "#5ee0c8";

export function TypeChip({ v }) {
  const video = v.kind === "video";
  return (
    <Chip color={video ? VIDEO_C : SHORT_C}>
      {video ? "Video" : "Short"}{v.duration_sec ? ` · ${fmtLen(v.duration_sec)}` : ""}
    </Chip>
  );
}

export function StatusPill({ v }) {
  if (v.status === "live") return <Chip tone="go">Live</Chip>;
  if (v.status === "scheduled") return <Chip tone="info">Scheduled {fmtWhen(v.publish_at)}</Chip>;
  if (v.status === "private") return <Chip tone="warn">Private</Chip>;
  if (v.status === "unlisted") return <Chip tone="info">Unlisted</Chip>;
  return <Chip tone="idle">Waiting for stats</Chip>;
}

/* A number cell that reads as "no data" rather than zero before stats arrive. */
export function N({ n, tone }) {
  if (n == null) return <span className="faint">–</span>;
  return <span style={tone ? { color: `var(--${tone})` } : undefined}>{fmtNum(n)}</span>;
}

export const signed = (n) => (n == null ? "" : `${n > 0 ? "+" : ""}${fmtNum(n)}`);

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"];
const dayLabel = (iso) => {
  const d = new Date(iso + "T00:00:00");
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
};

/* Total channel views over time, one point per day with a snapshot, with the
   long-form launches marked. */
export function GrowthChart({ points, markers = [] }) {
  if (!points?.length) return <p className="muted">No stats yet. Sync with YouTube to start the history.</p>;
  const W = 800, H = 260, L = 20, R = 740, T = 22, B = 222;
  const t = (iso) => new Date(iso + "T00:00:00").getTime();
  const t0 = t(points[0].day), t1 = Math.max(t(points[points.length - 1].day), t0 + 86400000);
  const vs = points.map((p) => p.views);
  const step = 10 ** Math.floor(Math.log10(Math.max(1, Math.max(...vs) - Math.min(...vs))));
  const lo = Math.floor(Math.min(...vs) / step) * step, hi = Math.ceil(Math.max(...vs) / step) * step || lo + step;
  const x = (iso) => L + ((t(iso) - t0) / (t1 - t0)) * (R - L);
  const y = (v) => B - ((v - lo) / (hi - lo)) * (B - T);
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(p.day).toFixed(1)},${y(p.views).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  const mid = points[Math.floor(points.length / 2)];
  const ticks = [hi, (hi + lo) / 2, lo];
  const short = (v) => (v >= 1000 ? `${(v / 1000).toFixed(v % 1000 ? 1 : 0)}K` : String(v));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" style={{ width: "100%", height: "auto" }}
         aria-label={`Total channel views rose from ${fmtNum(points[0].views)} on ${dayLabel(points[0].day)} to ${fmtNum(last.views)} on ${dayLabel(last.day)}`}>
      {ticks.map((v) => (
        <g key={v}>
          <line x1={L} x2={R} y1={y(v)} y2={y(v)} stroke="var(--line)" />
          <text x={R + 8} y={y(v) + 4} fontSize="11" fill="var(--muted)" fontFamily="var(--mono)">{short(v)}</text>
        </g>
      ))}
      {[points[0], mid, last].map((p, i) => (
        <text key={i} x={x(p.day)} y={H - 14} fontSize="11" fill="var(--muted)" fontFamily="var(--mono)"
              textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}>{dayLabel(p.day)}</text>
      ))}
      <path d={`${line} L${x(last.day)},${B} L${L},${B} Z`} fill="var(--go)" fillOpacity="0.08" />
      <path d={line} fill="none" stroke="var(--go)" strokeWidth="2.5" strokeLinejoin="round" />
      {markers.filter((m) => t(m.day) >= t0 && t(m.day) <= t1).map((m, i) => (
        <g key={m.day + m.label}>
          <line x1={x(m.day)} x2={x(m.day)} y1={T + 10} y2={B} stroke="#5ee0c8" strokeDasharray="3 4" />
          <text x={x(m.day) - 6} y={T + 24 + 16 * i} fontSize="12" fill="#5ee0c8" textAnchor="end">{m.label}</text>
        </g>
      ))}
      <circle cx={x(last.day)} cy={y(last.views)} r="4" fill="var(--go)" />
    </svg>
  );
}
