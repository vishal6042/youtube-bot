import Chip from "./Chip.jsx";
import PlaylistCover from "./PlaylistCover.jsx";

function tally(items) {
  const t = { uploaded: 0, ready: 0, rendered: 0, missing: 0 };
  for (const it of items) t[it.state]++;
  return t;
}

export default function PlaylistCards({ series, nextUp, onOpenPlaylist }) {
  const rankOf = new Map(nextUp.map((p, i) => [p.key, i + 1]));

  return (
    <section>
      <div className="section-title">PLAYLISTS · TAP A CARD TO DRILL IN</div>
      <div className="playlists">
        {series.map((s) => {
          const t = tally(s.items);
          const pct = s.total ? Math.round((s.uploaded / s.total) * 100) : 0;
          const queued = s.items
            .filter((it) => rankOf.has(it.key))
            .sort((a, b) => rankOf.get(a.key) - rankOf.get(b.key));
          return (
            <div
              className="pl-card clickable"
              key={s.series}
              role="button"
              tabIndex={0}
              onClick={() => onOpenPlaylist(s.series)}
              onKeyDown={(e) => e.key === "Enter" && onOpenPlaylist(s.series)}
            >
              <PlaylistCover series={s.series} />
              <div className="pl-head">
                <div>
                  <div className="pl-name">{s.playlist}</div>
                  <div className="pl-series">{s.series}</div>
                </div>
                <div className="pl-count">{s.uploaded}/{s.total} uploaded</div>
              </div>
              {!s.playlist_exists && (
                <div className="pl-warn">⚠ playlist not created on YouTube yet</div>
              )}
              <div className="pl-bar"><div style={{ width: pct + "%" }} /></div>
              <div className="pl-counts">
                <Chip cls="chip-uploaded">✅ {t.uploaded}</Chip>
                <Chip cls="chip-ready">⏳ {t.ready}</Chip>
                {t.rendered > 0 && <Chip cls="chip-rendered">🎬 {t.rendered}</Chip>}
                {t.missing > 0 && <Chip cls="chip-missing">⬜ {t.missing}</Chip>}
                {queued.length > 0 && <Chip cls="chip-queue">🎯 {queued.length} in queue</Chip>}
              </div>
              {queued.length > 0 && (
                <div className="pl-next">
                  Next in queue: <b>#{rankOf.get(queued[0].key)} {queued[0].title}</b>
                </div>
              )}
              <div className="pl-open">OPEN ▸</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
