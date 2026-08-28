/* The upload animation, shared by Upload Control and the Mission page.
 *
 * The render orchestrator is drawn as a network because renders run several
 * agents at once. Uploading is the opposite shape: strictly one video at a time,
 * with one step (the transfer) taking almost all the wall clock. So this is a
 * transmission arc — the local file on the left, the channel on the right, and
 * the five real stages the uploader reports as gates along the beam.
 */

export const STAGES = [
  { id: "authorising", label: "AUTH",      hint: "token + channel check" },
  { id: "uploading",   label: "TRANSFER",  hint: "the video file" },
  { id: "thumbnail",   label: "THUMBNAIL", hint: "custom thumbnail" },
  { id: "playlist",    label: "PLAYLIST",  hint: "add to its series" },
  { id: "recording",   label: "RECORD",    hint: "mark uploaded" },
];
const ORDER = ["starting", ...STAGES.map((s) => s.id), "done"];

export function mb(bytes) {
  return bytes ? `${(bytes / 1e6).toFixed(1)} MB` : "—";
}

export default function TransmissionArc({ item, run, channel = "Data in Motion" }) {
  const W = 900, H = 150;
  const y = 78, x0 = 120, x1 = W - 120;
  const active = run?.stage || (item ? "starting" : null);
  const idx = Math.max(0, ORDER.indexOf(active));
  const pct = run?.pct ?? 0;

  const gates = STAGES.map((s, i) => ({
    ...s,
    x: x0 + ((i + 1) / (STAGES.length + 1)) * (x1 - x0),
    state: ORDER.indexOf(s.id) < idx ? "done"
         : ORDER.indexOf(s.id) === idx ? "active" : "pending",
  }));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="ua-svg">
      <defs>
        <linearGradient id="ua-beam" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#38e1ff" />
          <stop offset="100%" stopColor="#35e0a1" />
        </linearGradient>
      </defs>

      {/* the rail, then the beam filled to real transfer progress */}
      <line x1={x0} y1={y} x2={x1} y2={y} stroke="rgba(72,118,190,0.25)" strokeWidth="3" />
      <line x1={x0} y1={y} x2={x0 + (x1 - x0) * (pct / 100)} y2={y}
            stroke="url(#ua-beam)" strokeWidth="3" strokeLinecap="round"
            className={run?.running ? "ua-beam-live" : ""} />

      <g>
        <rect x={x0 - 96} y={y - 30} width="86" height="60" rx="10"
              fill="rgba(6,10,20,0.8)" stroke="rgba(72,118,190,0.35)" />
        <text x={x0 - 53} y={y - 8} className="ua-end" textAnchor="middle">LOCAL</text>
        <text x={x0 - 53} y={y + 12} className="ua-end-sub" textAnchor="middle">
          {mb(item?.bytes)}
        </text>
      </g>

      <g>
        <rect x={x1 + 10} y={y - 30} width="96" height="60" rx="10"
              fill="rgba(6,10,20,0.8)" stroke="rgba(53,224,161,0.4)" />
        <text x={x1 + 58} y={y - 8} className="ua-end" textAnchor="middle">YOUTUBE</text>
        <text x={x1 + 58} y={y + 12} className="ua-end-sub" textAnchor="middle">{channel}</text>
      </g>

      {gates.map((g) => (
        <g key={g.id} className={"ua-gate " + g.state}>
          <circle cx={g.x} cy={y} r={g.state === "active" ? 11 : 8} />
          {g.state === "done" && (
            <text x={g.x} y={y + 4} className="ua-tick" textAnchor="middle">✓</text>
          )}
          <text x={g.x} y={y - 24} className="ua-gate-label" textAnchor="middle">{g.label}</text>
          {g.state === "active" && (
            <text x={g.x} y={y + 34} className="ua-gate-pct" textAnchor="middle">
              {g.id === "uploading" ? `${pct}%` : g.hint}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}
