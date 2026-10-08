import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import {
  Bar, Btn, Chip, Empty, Icon, PageHeader, Pager, Seg, Select, Stat, StatusChip,
  fmtNum, fmtWhen, playlistColor, usePaged,
} from "../ui.jsx";
import "../screens/learn.css";

const FILTERS = [
  { value: "all", label: "All" },
  { value: "queue", label: "Next up" },
  { value: "missing", label: "Planned" },
  { value: "rendered", label: "In review" },
  { value: "ready", label: "Ready" },
  { value: "uploaded", label: "Published" },
  { value: "discarded", label: "Discarded" },
];

function tally(items) {
  const t = { uploaded: 0, ready: 0, rendered: 0, missing: 0, discarded: 0 };
  for (const it of items) t[it.state] = (t[it.state] || 0) + 1;
  return t;
}

function progressLine(s, t) {
  const parts = [`${s.uploaded} of ${s.total} published`];
  if (t.ready) parts.push(`${t.ready} ready`);
  if (t.rendered) parts.push(`${t.rendered} in review`);
  if (t.missing) parts.push(`${t.missing} planned`);
  if (t.discarded) parts.push(`${t.discarded} discarded`);
  return parts.join(" · ");
}

/* The secondary actions of a row. Positioned with fixed coordinates taken from
   the trigger, because the table sits in a horizontal scroll box that would
   clip an absolutely positioned menu on the last rows. */
function RowMenu({ label, items }) {
  const [pos, setPos] = useState(null);
  const btn = useRef(null);
  const menu = useRef(null);

  useEffect(() => {
    if (!pos) return undefined;
    const close = () => setPos(null);
    const onDown = (e) => {
      if (!menu.current?.contains(e.target) && !btn.current?.contains(e.target)) close();
    };
    const onKey = (e) => {
      if (e.key !== "Escape") return;
      close();
      btn.current?.focus();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    // preventScroll: a scroll caused by taking focus would close the menu again.
    menu.current?.querySelector("button")?.focus({ preventScroll: true });
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [pos]);

  if (!items.length) return null;

  const toggle = () => {
    if (pos) return setPos(null);
    const r = btn.current.getBoundingClientRect();
    const right = window.innerWidth - r.right;
    const needed = items.length * 40 + 16;
    // Open upwards when there is no room below the trigger.
    return setPos(r.bottom + needed > window.innerHeight
      ? { right, bottom: window.innerHeight - r.top + 4 }
      : { right, top: r.bottom + 4 });
  };

  return (
    <>
      <button ref={btn} type="button" className="btn icon sm ghost" aria-label={label} title="More actions"
              aria-haspopup="menu" aria-expanded={!!pos} onClick={toggle}>
        <Icon name="more" />
      </button>
      {pos && (
        <div ref={menu} className="rowmenu" role="menu" aria-label={label} style={pos}>
          {items.map((m) => (
            <button key={m.label} type="button" role="menuitem"
                    onClick={() => { setPos(null); m.onClick(); }}>
              <Icon name={m.icon} />{m.label}
            </button>
          ))}
        </div>
      )}
    </>
  );
}

function EpisodeActions({ it, playlist, working, onMark, onOpen, onRender, onLink, onWatch }) {
  if (working) {
    return (
      <div className="row-actions">
        <Chip tone="go" plain>
          <span className="spin" style={{ width: 10, height: 10 }} aria-hidden="true" />Rendering
        </Chip>
      </div>
    );
  }

  const more = [];
  let primary = null;
  if (it.state === "uploaded") {
    if (it.url) {
      primary = (
        <a className="btn sm" href={it.url} target="_blank" rel="noopener noreferrer"
           aria-label={`Open ${it.title} on YouTube`}>
          <Icon name="external" />YouTube
        </a>
      );
      more.push({ label: "Edit link", icon: "edit", onClick: () => onLink(it.key, it.title) });
    } else {
      primary = <Btn size="sm" icon="plus" onClick={() => onLink(it.key, it.title)}>Add link</Btn>;
    }
  } else {
    const renderLabel = it.state === "missing" ? "Render" : "Re-render";
    const render = () => onRender(it.key, it.title);
    if (it.state === "ready") {
      primary = <Btn kind="primary" size="sm" icon="check" onClick={() => onMark(it.key, it.title)}>Mark published</Btn>;
      more.push({ label: renderLabel, icon: "refresh", onClick: render });
    } else if (it.state === "missing") {
      primary = <Btn size="sm" icon="play" onClick={render}>{renderLabel}</Btn>;
    } else {
      more.push({ label: renderLabel, icon: "refresh", onClick: render });
    }
  }
  if (it.exported) more.push({ label: "Open folder", icon: "folder", onClick: () => onOpen(it.exported) });

  return (
    <div className="row-actions">
      {it.state !== "missing" && (
        <Btn kind="ghost" size="sm" icon="play" iconOnly={`Play ${it.title}`}
             onClick={() => onWatch({ ...it, playlist })} />
      )}
      {primary}
      <RowMenu label={`More actions for ${it.title}`} items={more} />
    </div>
  );
}

function PlaylistDetail({ s, stats, rankOf, workingKey, onPlaylistCreated, handlers }) {
  const [filter, setFilter] = useState("all");
  const color = playlistColor(s.series);

  const counts = useMemo(() => {
    const t = tally(s.items);
    return { ...t, all: s.items.length, queue: s.items.filter((it) => rankOf.has(it.key)).length };
  }, [s.items, rankOf]);

  // A filter carried over from another playlist may match nothing here.
  const active = counts[filter] ? filter : "all";
  const rows = useMemo(() => {
    if (active === "all") return s.items;
    if (active === "queue") {
      return s.items.filter((it) => rankOf.has(it.key))
        .sort((a, b) => rankOf.get(a.key) - rankOf.get(b.key));
    }
    return s.items.filter((it) => it.state === active);
  }, [s.items, active, rankOf]);

  const p = usePaged(rows, 10, `${s.series}|${active}`);
  const options = FILTERS
    .filter((f) => f.value === "all" || counts[f.value] > 0)
    .map((f) => ({ ...f, count: counts[f.value] || 0 }));

  return (
    <section className="card" style={{ borderTop: `3px solid ${color}` }} aria-label={`${s.playlist} episodes`}>
      <div className="card-head" style={{ flexWrap: "wrap" }}>
        <div style={{ minWidth: 0 }}>
          <h2 style={{ fontSize: 20 }}>{s.playlist}</h2>
          <div className="muted" style={{ fontSize: 13 }}>
            {s.playlist_exists ? "On YouTube" : "Not on YouTube yet"} · {progressLine(s, counts)}
          </div>
        </div>
        <span className="spacer" />
        {!s.playlist_exists && (
          <Btn size="sm" icon="check" onClick={() => onPlaylistCreated(s.series, s.playlist, true)}>
            Mark as created on YouTube
          </Btn>
        )}
        {s.playlist_exists && s.created_manually && (
          <Btn size="sm" kind="ghost" icon="undo" onClick={() => onPlaylistCreated(s.series, s.playlist, false)}>
            Mark as not created
          </Btn>
        )}
      </div>

      <p className={s.description ? "muted" : "faint"} style={{ fontSize: 13, marginBottom: 14, maxWidth: "80ch" }}>
        {s.description || "No description yet. Add one in Settings so it is ready to paste on YouTube."}
      </p>

      {stats && (
        <div className="cols c4" style={{ marginBottom: 14 }}>
          <Stat card={false} small label="Median views"
                value={stats.median_views != null ? fmtNum(Math.round(stats.median_views)) : "n/a"} />
          <Stat card={false} small label="Total views"
                value={stats.total_views != null ? fmtNum(stats.total_views) : "n/a"} />
          <Stat card={false} small label="Videos with stats" value={fmtNum(stats.videos)} />
        </div>
      )}

      <div className="rowf" style={{ marginBottom: 10 }}>
        <Seg value={active} onChange={setFilter} options={options} label="Episode status" />
      </div>

      <div className="scroll">
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 48 }}>#</th>
              <th>Episode</th>
              <th>Status</th>
              <th>Published</th>
              <th className="r"><span className="sr">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {p.slice.map((it) => (
              <tr key={it.key}>
                <td className="num faint">{String(it.episode ?? "").padStart(2, "0")}</td>
                <td>
                  <div className="rowf" style={{ gap: 8 }}>
                    <span className="t">{it.title}</span>
                    {rankOf.has(it.key) && <Chip tone="go" plain>Next up <span className="num">#{rankOf.get(it.key)}</span></Chip>}
                  </div>
                  <div className="k">{it.key}</div>
                </td>
                <td><StatusChip state={it.state} /></td>
                <td className="num muted">{it.uploaded_at ? fmtWhen(it.uploaded_at, { time: false }) : ""}</td>
                <td>
                  <EpisodeActions it={it} playlist={s.playlist} working={workingKey === it.key} {...handlers} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!rows.length && <Empty icon="playlists" title="No episodes here yet" />}
      <Pager p={p} noun="episodes" sizes={[10, 25]} />
    </section>
  );
}

export default function PlaylistsPage({
  series, nextUp, workingKey, selected, onSelect, onPlaylistCreated,
  onMark, onOpen, onRender, onLink, onWatch,
}) {
  const [sortChoice, setSortChoice] = useState(null);
  const [bySeries, setBySeries] = useState(null); // analytics rows by series key, null when unavailable

  useEffect(() => {
    let alive = true;
    api("/api/analytics")
      .then((d) => {
        if (alive && d.available) setBySeries(new Map(d.by_series.map((r) => [r.series, r])));
      })
      .catch(() => { /* the page works without view numbers */ });
    return () => { alive = false; };
  }, []);

  const rankOf = useMemo(() => new Map((nextUp || []).map((q, i) => [q.key, i + 1])), [nextUp]);

  const sort = sortChoice && (sortChoice !== "median" || bySeries) ? sortChoice : bySeries ? "median" : "default";
  const sorted = useMemo(() => {
    const list = [...(series || [])];
    if (sort === "median") {
      const m = (s) => bySeries.get(s.series)?.median_views ?? -1;
      list.sort((a, b) => m(b) - m(a));
    } else if (sort === "left") {
      list.sort((a, b) => (b.total - b.uploaded) - (a.total - a.uploaded));
    }
    return list;
  }, [series, sort, bySeries]);

  const current = sorted.find((s) => s.series === selected) || sorted[0];
  const sortOptions = [
    ...(bySeries ? [{ value: "median", label: "Best median views first" }] : []),
    { value: "left", label: "Most left to post" },
    { value: "default", label: "Default order" },
  ];

  return (
    <>
      <PageHeader title="Playlists"
                  sub={`${sorted.length} series. Select one to see its episodes below.`}>
        <Select label="Sort playlists" value={sort} onChange={setSortChoice} options={sortOptions} />
      </PageHeader>

      {!sorted.length && (
        <section className="card"><Empty icon="playlists" title="No playlists yet" /></section>
      )}

      {sorted.length > 0 && (
        <section className="cols" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))" }}
                 aria-label="All playlists">
          {sorted.map((s) => {
            const color = playlistColor(s.series);
            const median = bySeries?.get(s.series)?.median_views;
            const next = s.items
              .filter((it) => rankOf.has(it.key))
              .sort((a, b) => rankOf.get(a.key) - rankOf.get(b.key))[0];
            return (
              <button key={s.series} type="button" className="card lift plc" style={{ "--c": color }}
                      aria-pressed={current?.series === s.series} onClick={() => onSelect(s.series)}>
                <span className="plc-head">
                  <b>{s.playlist}</b>
                  {median != null && (
                    <span className="num" style={{ color: "var(--c)" }}
                          title="Median views per video"
                          aria-label={`${fmtNum(Math.round(median))} median views per video`}>
                      {fmtNum(Math.round(median))}
                    </span>
                  )}
                  {!s.playlist_exists && <Chip tone="warn" plain>Not on YouTube</Chip>}
                </span>
                <Bar pct={s.total ? (s.uploaded / s.total) * 100 : 0} color={color} style={{ width: "100%" }} />
                <span className="plc-line">{progressLine(s, tally(s.items))}</span>
                {next && <span className="plc-next">Next up: {next.title}</span>}
              </button>
            );
          })}
        </section>
      )}

      {bySeries && sorted.length > 0 && (
        <p className="faint" style={{ fontSize: 12.5, marginTop: -8 }}>
          The coloured number is the playlist's median views per video.
        </p>
      )}

      {current && (
        <PlaylistDetail s={current} stats={bySeries?.get(current.series)}
                        rankOf={rankOf} workingKey={workingKey} onPlaylistCreated={onPlaylistCreated}
                        handlers={{ onMark, onOpen, onRender, onLink, onWatch }} />
      )}
    </>
  );
}
