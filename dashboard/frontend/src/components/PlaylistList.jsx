import Chip from "./Chip.jsx";
import PlaylistCover from "./PlaylistCover.jsx";

function tally(items) {
  const t = { uploaded: 0, ready: 0, rendered: 0, missing: 0 };
  for (const it of items) t[it.state]++;
  return t;
}

/* Home page: one full-width card listing every playlist. The header opens the
   Playlists page; a row opens that playlist's detail page. */
export default function PlaylistList({ series, nextUp, onOpenPlaylist, onViewAll, onPlaylistCreated }) {
  const rankOf = new Map(nextUp.map((p, i) => [p.key, i + 1]));

  return (
    <section className="panel pll-panel">
      <div className="jobs-head">
        <span className="panel-title">PLAYLISTS</span>
        <button className="btn btn-mini" onClick={onViewAll}>VIEW ALL ▸</button>
      </div>

      <div className="pll-rows">
        {series.map((s) => {
          const t = tally(s.items);
          const pct = s.total ? Math.round((s.uploaded / s.total) * 100) : 0;
          const queued = s.items
            .filter((it) => rankOf.has(it.key))
            .sort((a, b) => rankOf.get(a.key) - rankOf.get(b.key));
          const next = queued[0];

          return (
            <button
              key={s.series}
              className="pll-row"
              onClick={() => onOpenPlaylist(s.series)}
            >
              <span className="pll-cover"><PlaylistCover series={s.series} /></span>

              <span className="pll-main">
                <span className={"pll-name chip-pl pl-" + s.series}>
                  {s.playlist}
                  {!s.playlist_exists && (
                    <>
                      <span className="pll-warn">⚠ not on YouTube</span>
                      <button
                        className="btn btn-mini pll-created"
                        title="Mark this playlist as created on YouTube"
                        onClick={(e) => {
                          e.stopPropagation();
                          onPlaylistCreated(s.series, s.playlist);
                        }}
                      >
                        ✓ CREATED
                      </button>
                    </>
                  )}
                </span>
                <span className="pll-sub">
                  {next
                    ? <>Next in queue: <b>#{rankOf.get(next.key)} {next.title}</b></>
                    : s.uploaded === s.total
                      ? "All episodes uploaded"
                      : "Nothing queued"}
                </span>
              </span>

              <span className="pll-progress">
                <span className="pll-bar"><span style={{ width: pct + "%" }} /></span>
                <span className="pll-count">{s.uploaded}/{s.total} uploaded</span>
              </span>

              <span className="pll-chips">
                <Chip cls="chip-uploaded">✅ {t.uploaded}</Chip>
                <Chip cls="chip-ready">⏳ {t.ready}</Chip>
                {t.missing > 0 && <Chip cls="chip-missing">⬜ {t.missing}</Chip>}
                {queued.length > 0 && <Chip cls="chip-queue">🎯 {queued.length}</Chip>}
              </span>

              <span className="pll-chev">▸</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
