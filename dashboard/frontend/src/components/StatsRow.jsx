import { useEffect, useState } from "react";
import { api } from "../api.js";

const fmt = (n) =>
  n == null ? "—" : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M`
  : n >= 1e3 ? `${(n / 1e3).toFixed(1)}K` : String(n);

export default function StatsRow({ counts }) {
  // Live channel numbers from the last YouTube sync (stored snapshot — free).
  // The sidebar footer keeps the operational inventory, so this row shows the
  // outcome: is the channel actually growing?
  const [yt, setYt] = useState(null);
  useEffect(() => {
    api("/api/yt/stats").then((r) => setYt(r.channel)).catch(() => {});
  }, []);

  const tiles = yt
    ? [
        [fmt(yt.subscribers), "👥 SUBSCRIBERS"],
        [fmt(yt.views), "▶ TOTAL VIEWS"],
        [fmt(yt.video_count), "📺 VIDEOS LIVE"],
        [counts.ready, "⏳ READY TO POST"],
      ]
    : [
        [counts.uploaded, "✅ UPLOADED"],
        [counts.ready, "⏳ READY"],
        [counts.rendered, "🎬 RENDERED"],
        [counts.total, "◈ TOPICS"],
      ];

  return (
    <section
      className="stats"
      title={yt ? `YouTube numbers from last sync: ${(yt.fetched_at || "").replace("T", " ")}` : undefined}
    >
      {tiles.map(([num, label]) => (
        <div className="stat" key={label}>
          <div className="stat-num">{num}</div>
          <div className="stat-label">{label}</div>
        </div>
      ))}
    </section>
  );
}
