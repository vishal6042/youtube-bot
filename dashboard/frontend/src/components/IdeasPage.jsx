import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import {
  Btn, Chip, Empty, Icon, MODE_LABEL, PageHeader, Pager, PlaylistChip, Select,
  SkeletonRows, Tabs, fmtNum, usePaged,
} from "../ui.jsx";
import "../screens/plan.css";

const ADDED = "__added";

const SORTS = [
  { value: "suggested", label: "Suggested order" },
  { value: "title", label: "Title A to Z" },
  { value: "chart", label: "Chart type" },
];

const modeLabel = (m) => MODE_LABEL[m] || m;

/* What to build next, one card per fully configured topic. Adding one only
   writes it into the catalog; it then waits in Topics as Planned. */
export default function IdeasPage({ toast, refresh, onOpenTopics }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [checks, setChecks] = useState({});   // id -> verify result
  const [busy, setBusy] = useState(null);     // { id, what }
  const [tab, setTab] = useState("all");
  const [sort, setSort] = useState("suggested");

  const load = useCallback(async () => {
    try {
      setData(await api("/api/ideas"));
      setFailed(false);
    } catch (e) {
      setFailed(true);
      toast(e.message, true);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const verify = async (idea) => {
    setBusy({ id: idea.id, what: "check" });
    try {
      const r = await api("/api/ideas/verify", { id: idea.id });
      setChecks((c) => ({ ...c, [idea.id]: r }));
      toast(r.ok ? `Source is fine for "${idea.title}"` : `Source failed: ${r.error}`, !r.ok);
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(null);
  };

  const add = async (idea) => {
    setBusy({ id: idea.id, what: "add" });
    try {
      await api("/api/ideas/accept", { id: idea.id, render: false });
      toast(`"${idea.title}" added to the plan. Render it from Topics.`);
      await load();
      refresh();
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(null);
  };

  const groups = data?.groups || [];
  // Flattening the groups keeps the server's order: playlist with the most
  // suggestions first, ideas in their curated order inside it.
  const ordered = useMemo(() => {
    const fromGroups = groups.flatMap((g) => g.ideas);
    return fromGroups.length ? fromGroups : data?.ideas || [];
  }, [data]);                                  // eslint-disable-line react-hooks/exhaustive-deps
  const ready = ordered.filter((i) => i.state === "ready");
  const added = ordered.filter((i) => i.state === "exists");
  const groupOf = (series) => groups.find((g) => g.series === series);

  // A playlist tab disappears once its last suggestion is added.
  const tabOk = tab === "all" || (tab === ADDED ? added.length > 0 : (groupOf(tab)?.ready || 0) > 0);
  const cur = tabOk ? tab : "all";

  const shown = useMemo(() => {
    const base = cur === ADDED ? added : cur === "all" ? ready : ready.filter((i) => i.series === cur);
    if (sort === "title") return [...base].sort((a, b) => a.title.localeCompare(b.title));
    if (sort === "chart") return [...base].sort((a, b) => modeLabel(a.mode).localeCompare(modeLabel(b.mode)));
    return base;
  }, [data, cur, sort]);                       // eslint-disable-line react-hooks/exhaustive-deps

  const paged = usePaged(shown, 6, `${cur}|${sort}`);

  if (!data) {
    return (
      <>
        <PageHeader title="Ideas" sub="Suggested topics, fully set up" />
        <section className="card" aria-label="Ideas">
          {failed ? (
            <Empty icon="alert" title="Could not load ideas"
                   action={<Btn size="sm" icon="refresh" onClick={load}>Try again</Btn>}>
              The dashboard server did not answer.
            </Empty>
          ) : <SkeletonRows rows={6} />}
        </section>
      </>
    );
  }

  const tabs = [
    { value: "all", label: "All", count: ready.length },
    ...groups.filter((g) => g.ready > 0).map((g) => ({ value: g.series, label: g.playlist, count: g.ready })),
    ...(added.length ? [{ value: ADDED, label: "Already added", count: added.length }] : []),
  ];
  const curGroup = cur !== "all" && cur !== ADDED ? groupOf(cur) : null;

  return (
    <>
      <PageHeader
        title="Ideas"
        sub={`${ready.length} suggested topic${ready.length === 1 ? "" : "s"}, fully set up. `
          + "Add the ones you want; they move to Topics as Planned."}
      >
        <Select label="Sort ideas" value={sort} onChange={setSort} options={SORTS} />
        <Btn onClick={onOpenTopics}>
          Open topics <span className="num faint">{fmtNum(data.catalog_size)}</span>
        </Btn>
      </PageHeader>

      <Tabs label="Playlist" value={cur} onChange={setTab} options={tabs} />

      <div className="split">
        <div className="wide stack" style={{ gap: 18 }}>
          {curGroup && (
            <div className="rowf muted" style={{ fontSize: 13 }}>
              <span>
                {curGroup.in_catalog} topic{curGroup.in_catalog === 1 ? "" : "s"} already in this playlist
              </span>
              {!curGroup.playlist_exists && <Chip tone="warn" plain>Playlist not on YouTube yet</Chip>}
            </div>
          )}
          {cur === ADDED && (
            <div className="muted" style={{ fontSize: 13 }}>
              These are already in Topics. Anything not rendered yet is listed there as Planned,
              where it can still be removed.{" "}
              <button type="button" className="link" onClick={onOpenTopics}>Open topics</button>
            </div>
          )}

          {!shown.length ? (
            <div className="card">
              <Empty icon="ideas" title="No suggestions left here"
                     action={<Btn size="sm" onClick={onOpenTopics}>Open topics</Btn>}>
                Every idea has been added to the plan.
              </Empty>
            </div>
          ) : (
            <div className="cols c2 idea-grid">
              {paged.slice.map((idea) => {
                const check = checks[idea.id];
                const working = busy?.id === idea.id;
                const group = groupOf(idea.series);
                return (
                  <article className="card lift stack idea" key={idea.id}>
                    <div className="rowf">
                      <PlaylistChip series={idea.series} name={idea.playlist} />
                      {idea.state === "exists" && <Chip tone="go" plain>In topics</Chip>}
                      {group && !group.playlist_exists && cur === "all" && (
                        <Chip tone="warn" plain>Playlist not on YouTube yet</Chip>
                      )}
                    </div>
                    <div>
                      <h2>{idea.title}</h2>
                      <div className="k">{idea.key}</div>
                    </div>
                    {idea.subtitle && <p>{idea.subtitle}</p>}
                    <p className="muted">{idea.reason}</p>
                    <div className="rowf faint idea-meta">
                      <span>{modeLabel(idea.mode)}</span>
                      {idea.source && <><span aria-hidden="true">·</span><span title={idea.code || undefined}>{idea.source}</span></>}
                    </div>

                    {check && (
                      <div className={"idea-check " + (check.ok ? "ok" : "bad")} role="status">
                        <Icon name={check.ok ? "check" : "alert"} />
                        <span>
                          {!check.ok ? `Source failed: ${check.error}`
                            : check.note ? check.note
                            : `Source checked: ${fmtNum(check.rows)} rows${check.years ? `, ${check.years}` : ""}`
                              + (check.entities != null ? `, ${fmtNum(check.entities)} entities` : "")}
                        </span>
                      </div>
                    )}

                    {idea.state === "ready" && (
                      <div className="rowf idea-foot">
                        <Btn kind="primary" size="sm" icon="plus" disabled={working} onClick={() => add(idea)}>
                          {working && busy.what === "add" ? "Adding" : "Add to plan"}
                        </Btn>
                        <Btn kind="ghost" size="sm" disabled={working} onClick={() => verify(idea)}>
                          {working && busy.what === "check" ? "Checking" : "Check source"}
                        </Btn>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </div>

        <div className="rail">
          <section className="card" aria-label="Series that need writing">
            <div className="card-head"><h2>Needs a script first</h2></div>
            {data.authored?.length ? (
              <div className="stack" style={{ gap: 14 }}>
                {data.authored.map((s) => (
                  <div key={s.name}>
                    <div className="rowf" style={{ justifyContent: "space-between" }}>
                      <b>{s.name}</b>
                      <span className="num muted" style={{ fontSize: 13 }}>{s.episodes} episodes</span>
                    </div>
                    <div className="muted" style={{ fontSize: 13 }}>{s.note}</div>
                    <div className="plan-doc">{s.doc}</div>
                  </div>
                ))}
                <p className="faint" style={{ fontSize: 12.5 }}>
                  These are narrated animations, not data charts. Each episode needs its scene
                  written in code before it can be rendered, so they cannot be added in one click.
                </p>
              </div>
            ) : (
              <p className="muted" style={{ fontSize: 13 }}>Nothing is waiting on a script.</p>
            )}
          </section>
        </div>
      </div>

      <Pager p={paged} noun={cur === ADDED ? "already added" : "ideas"} sizes={null} />
    </>
  );
}
