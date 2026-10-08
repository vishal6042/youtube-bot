import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import {
  Banner, Btn, Chip, Empty, Icon, MODE_LABEL, PageHeader, Pager, PlaylistChip, STATUS,
  Search, Seg, Select, SkeletonRows, StatusChip, fmtSecs, fmtWhen, usePaged,
} from "../ui.jsx";
import "../screens/plan.css";

// Approved and Rejected are usually empty, so they only get a filter button
// while they have topics in them.
const PHASES = ["planned", "draft", "approved", "ready", "uploaded", "rejected"];
const ALWAYS = new Set(["planned", "draft", "ready", "uploaded"]);
const PHASE_LABEL = { ready: "Ready" };
const phaseLabel = (p) => PHASE_LABEL[p] || STATUS[p]?.[0] || p;
const modeLabel = (m) => MODE_LABEL[m] || m;

/* Per-row overflow menu. items: [{ label, icon, onClick | href, danger }] */
function RowMenu({ label, items }) {
  const [pos, setPos] = useState(null);
  const btnRef = useRef(null);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!pos) return;
    menuRef.current?.querySelector("button, a")?.focus();
    const close = () => setPos(null);
    const onDown = (e) => {
      if (!menuRef.current?.contains(e.target) && !btnRef.current?.contains(e.target)) close();
    };
    const onKey = (e) => {
      if (e.key !== "Escape") return;
      close();
      btnRef.current?.focus();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    // The menu is fixed to where the button was, so it must not outlive a scroll.
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [pos]);

  const toggle = () => {
    if (pos) return setPos(null);
    const r = btnRef.current.getBoundingClientRect();
    const right = Math.max(8, window.innerWidth - r.right);
    // Open upwards when there is no room below the button.
    const below = window.innerHeight - r.bottom > items.length * 40 + 24;
    setPos(below ? { top: r.bottom + 4, right } : { bottom: window.innerHeight - r.top + 4, right });
  };

  return (
    <>
      <button ref={btnRef} type="button" className="btn icon sm ghost" aria-label={label} title="More actions"
              aria-haspopup="true" aria-expanded={!!pos} onClick={toggle}>
        <Icon name="more" />
      </button>
      {pos && (
        <div ref={menuRef} className="row-menu" style={pos}>
          {items.map((it) => it.href ? (
            <a key={it.label} href={it.href} target="_blank" rel="noopener noreferrer"
               onClick={() => setPos(null)}>
              <Icon name={it.icon} />{it.label}
            </a>
          ) : (
            <button key={it.label} type="button" className={it.danger ? "danger" : ""}
                    onClick={() => { setPos(null); it.onClick(); }}>
              <Icon name={it.icon} />{it.label}
            </button>
          ))}
        </div>
      )}
    </>
  );
}

export default function TopicsPage({
  workingKey, onRender, onRenderMany, onOpen, onWatch, onRemove, onBrowseIdeas,
  promptText, confirm, toast, initialQuery,
}) {
  const [topics, setTopics] = useState(null);
  const [failed, setFailed] = useState(false);
  const [phase, setPhase] = useState("all");
  const [query, setQuery] = useState(initialQuery || "");
  const [series, setSeries] = useState("");
  const [mode, setMode] = useState("");
  const [picked, setPicked] = useState(() => new Set());
  const [sending, setSending] = useState(false);

  const refetch = useCallback(async () => {
    try {
      const r = await api("/api/topics");
      setTopics(r.topics);
      setFailed(false);
    } catch (e) {
      setFailed(true);
      toast(e.message, true);
    }
  }, [toast]);

  // Also re-read when a render starts or finishes, so phases stay current.
  useEffect(() => { refetch(); }, [refetch, workingKey]);

  // A new global search replaces whatever was filtered before.
  useEffect(() => {
    if (initialQuery == null) return;
    setQuery(initialQuery);
    if (initialQuery) { setPhase("all"); setSeries(""); setMode(""); }
  }, [initialQuery]);

  const act = async (fn, okMsg) => {
    try {
      await fn();
      if (okMsg) toast(okMsg);
      refetch();
    } catch (e) {
      toast(e.message, true);
    }
  };

  const review = (t, action, note) =>
    act(() => api("/api/review", { key: t.key, action, note }),
        `${action === "approve" ? "Approved" : "Rejected"} "${t.title}"`);

  const reject = async (t) => {
    const note = await promptText({
      title: "Reject this draft?",
      message: `"${t.title}" will be marked rejected.`,
      input: { label: "Reason (optional)", placeholder: "e.g. data looks wrong" },
      confirmLabel: "Reject", tone: "danger",
    });
    if (note === null) return;
    review(t, "reject", note || null);
  };

  const doExport = (t) =>
    act(() => api("/api/export", { key: t.key }), `Exported "${t.title}" for upload`);

  const remove = (t) => act(() => onRemove(t.key, t.title), null);

  const canRender = (t) => (t.phase === "planned" || t.phase === "rejected") && workingKey !== t.key;

  const all = topics || [];
  const counts = useMemo(() => {
    const c = { all: all.length };
    for (const t of all) c[t.phase] = (c[t.phase] || 0) + 1;
    return c;
  }, [topics]);                                // eslint-disable-line react-hooks/exhaustive-deps

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return all.filter((t) =>
      (phase === "all" || t.phase === phase)
      && (!series || t.series === series)
      && (!mode || t.mode === mode)
      && (!q || `${t.title} ${t.key} ${t.subtitle || ""}`.toLowerCase().includes(q)));
  }, [topics, phase, series, mode, query]);    // eslint-disable-line react-hooks/exhaustive-deps

  const paged = usePaged(rows, 10, `${phase}|${series}|${mode}|${query}`);

  // Selection is kept as keys; anything that stopped being renderable (it was
  // rendered, removed, or is rendering now) silently drops out.
  const selected = all.filter((t) => picked.has(t.key) && canRender(t));
  const pageKeys = paged.slice.filter(canRender).map((t) => t.key);
  const pageAllOn = pageKeys.length > 0 && pageKeys.every((k) => picked.has(k));

  const togglePick = (key) => setPicked((s) => {
    const n = new Set(s);
    n.has(key) ? n.delete(key) : n.add(key);
    return n;
  });
  const togglePage = () => setPicked((s) => {
    const n = new Set(s);
    pageKeys.forEach((k) => (pageAllOn ? n.delete(k) : n.add(k)));
    return n;
  });

  const renderSelected = async () => {
    const n = selected.length;
    const ok = await confirm({
      title: `Render ${n} topic${n === 1 ? "" : "s"}?`,
      message: "Each one runs the full pipeline, one after another, and lands in review when it is done.",
      items: selected.map((t) => ({ title: t.title, meta: t.playlist })),
      confirmLabel: "Render selected",
    });
    if (!ok) return;
    setSending(true);
    try {
      await onRenderMany(selected.map((t) => t.key));
      setPicked(new Set());
      refetch();
    } catch (e) {
      toast(e.message, true);
    }
    setSending(false);
  };

  const header = (
    <PageHeader title="Topics" sub="Every topic and where it is: planned, in review, ready or published">
      <Btn icon="ideas" onClick={onBrowseIdeas}>Browse ideas</Btn>
    </PageHeader>
  );

  if (!topics) {
    return (
      <>
        {header}
        <section className="card" style={{ padding: "8px 8px 16px" }} aria-label="Topics">
          {failed ? (
            <Empty icon="alert" title="Could not load topics"
                   action={<Btn size="sm" icon="refresh" onClick={refetch}>Try again</Btn>}>
              The dashboard server did not answer.
            </Empty>
          ) : <SkeletonRows rows={8} />}
        </section>
      </>
    );
  }

  const phaseOptions = [
    { value: "all", label: "All", count: counts.all },
    ...PHASES.filter((p) => ALWAYS.has(p) || counts[p] || phase === p)
      .map((p) => ({ value: p, label: phaseLabel(p), count: counts[p] || 0 })),
  ];
  const playlistOptions = [
    { value: "", label: "All playlists" },
    ...[...new Map(all.map((t) => [t.series, t.playlist || t.series]))]
      .map(([value, label]) => ({ value, label })),
  ];
  const modeOptions = [
    { value: "", label: "Any chart" },
    ...[...new Set(all.map((t) => t.mode))].map((m) => ({ value: m, label: modeLabel(m) })),
  ];
  const filtered = phase !== "all" || series || mode || query.trim();
  const clearFilters = () => { setPhase("all"); setSeries(""); setMode(""); setQuery(""); };

  // One visible button for the obvious next step; the rest go in the menu.
  const actionsFor = (t) => {
    const watch = t.video && t.phase !== "planned"
      ? { label: "Watch", icon: "play", onClick: () => onWatch(t) } : null;
    const more = [];
    let main = null;
    if (t.phase === "planned" || t.phase === "rejected") {
      main = { label: t.phase === "rejected" ? "Render again" : "Render", icon: "play",
               onClick: () => onRender(t.key, t.title) };
      if (watch) more.push(watch);
    } else if (t.phase === "draft") {
      main = { label: "Approve", icon: "check", kind: "primary", onClick: () => review(t, "approve") };
      if (watch) more.push(watch);
      more.push({ label: "Reject", icon: "close", danger: true, onClick: () => reject(t) });
    } else if (t.phase === "approved") {
      main = { label: "Export", icon: "upload", kind: "primary", onClick: () => doExport(t) };
      if (watch) more.push(watch);
    } else if (t.phase === "ready") {
      if (t.exported) main = { label: "Open folder", icon: "folder", onClick: () => onOpen(t.exported) };
      if (watch) more.push(watch);
    } else {
      main = watch;
    }
    if (t.url) more.push({ label: "Open on YouTube", icon: "external", href: t.url });
    if (t.phase === "planned") {
      more.push({ label: "Remove topic", icon: "trash", danger: true, onClick: () => remove(t) });
    }
    return { main, more };
  };

  const rendered = (t) => {
    if (t.render_date) {
      return (
        <>
          {fmtWhen(t.render_date, { time: false })}
          {t.duration_sec ? <span className="num faint"> · {fmtSecs(t.duration_sec)}</span> : null}
        </>
      );
    }
    // A published video with no render on disk had its working files purged;
    // calling that "never rendered" would be wrong.
    if (t.phase === "uploaded") return <span className="faint">Files cleaned up</span>;
    return <span className="faint">Not yet</span>;
  };

  return (
    <>
      {header}

      <div className="rowf">
        <Seg label="Status" value={phase} onChange={setPhase} options={phaseOptions} />
        <span className="spacer" />
        <Search value={query} onChange={setQuery} placeholder="Search title or key" label="Search topics" />
        <Select label="Playlist" value={series} onChange={setSeries} options={playlistOptions} />
        <Select label="Chart type" value={mode} onChange={setMode} options={modeOptions} />
      </div>

      {selected.length > 0 && (
        <Banner
          tone="go"
          title={`${selected.length} selected`}
          actions={
            <>
              <Btn kind="ghost" size="sm" onClick={() => setPicked(new Set())}>Clear</Btn>
              <Btn kind="primary" size="sm" icon="play" disabled={sending} onClick={renderSelected}>
                {sending ? "Queueing" : "Render selected"}
              </Btn>
            </>
          }
        >
          Rendered one after another. Only planned and rejected topics can be selected.
        </Banner>
      )}

      <section className="card" style={{ padding: "8px 8px 16px" }}
               aria-label={phase === "all" ? "All topics" : `${phaseLabel(phase)} topics`}>
        {!rows.length ? (
          all.length ? (
            <Empty icon="search" title="No topics match"
                   action={filtered && <Btn size="sm" onClick={clearFilters}>Clear filters</Btn>}>
              Try a different status, playlist or search.
            </Empty>
          ) : (
            <Empty icon="topics" title="No topics yet"
                   action={<Btn size="sm" kind="primary" onClick={onBrowseIdeas}>Browse ideas</Btn>}>
              Add a few from Ideas to start the plan.
            </Empty>
          )
        ) : (
          <>
            <div className="scroll">
              <table className="tbl">
                <thead>
                  <tr>
                    <th style={{ width: 40 }}>
                      <input className="check" type="checkbox" aria-label="Select all renderable topics on this page"
                             checked={pageAllOn} disabled={!pageKeys.length} onChange={togglePage} />
                    </th>
                    <th>Topic</th>
                    <th>Playlist</th>
                    <th>Chart</th>
                    <th>Status</th>
                    <th>Rendered</th>
                    <th className="r"><span className="sr">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {paged.slice.map((t) => {
                    const working = workingKey === t.key;
                    const on = picked.has(t.key) && canRender(t);
                    const { main, more } = actionsFor(t);
                    return (
                      <tr key={t.key} className={on ? "sel" : ""}>
                        <td>
                          <input className="check" type="checkbox" checked={on} disabled={!canRender(t)}
                                 aria-label={`Select ${t.title}`}
                                 title={canRender(t) ? undefined : "Only planned and rejected topics can be rendered"}
                                 onChange={() => togglePick(t.key)} />
                        </td>
                        <td className="topic-cell">
                          <div className="t">{t.title}</div>
                          <div className="k">{t.key}</div>
                          {t.note && <div className="topic-note">Note: {t.note}</div>}
                        </td>
                        <td>
                          <PlaylistChip series={t.series} name={t.playlist} />
                          {t.episode != null && t.episode !== "" && (
                            <div className="faint" style={{ fontSize: 12, marginTop: 4 }}>Episode {t.episode}</div>
                          )}
                        </td>
                        <td className="muted">{modeLabel(t.mode)}</td>
                        <td><StatusChip state={t.phase} /></td>
                        <td className="muted" style={{ whiteSpace: "nowrap" }}>{rendered(t)}</td>
                        <td>
                          <div className="topic-actions">
                            {working ? (
                              <Chip tone="go" plain><span className="spin" aria-hidden="true" />Rendering</Chip>
                            ) : (
                              <>
                                {main && (
                                  <Btn size="sm" kind={main.kind || ""} icon={main.icon} onClick={main.onClick}>
                                    {main.label}
                                  </Btn>
                                )}
                                {more.length > 0 && <RowMenu label={`More actions for ${t.title}`} items={more} />}
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pager p={paged} noun={phase === "all" ? "topics" : phaseLabel(phase).toLowerCase()}
                   style={{ padding: "14px 12px 0" }} />
          </>
        )}
      </section>
    </>
  );
}
