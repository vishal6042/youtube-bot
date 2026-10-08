import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import {
  Banner, Btn, Chip, Empty, Icon, PageHeader, Pager, Search, SkeletonRows, Tabs, usePaged,
} from "../ui.jsx";
import "../screens/library.css";

/* The API lists the moods but not what they are for, so that lives here. */
const MOOD_INFO = {
  calm: "population, life, people",
  hopeful: "science, tech, energy, innovation",
  reflective: "CO₂, military, migration",
  majestic: "GDP, exports, economy",
  serene: "travel, nature, food",
  lofi: "developers, phones, internet",
  untagged: "fallback for any mood",
};

const moodName = (m) => (m === "untagged" ? "No mood" : m.charAt(0).toUpperCase() + m.slice(1));
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function clock(s) {
  if (s == null || !isFinite(s)) return "";
  const t = Math.round(s);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

function splitName(name) {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? [name.slice(0, dot), name.slice(dot + 1).toLowerCase()] : [name, ""];
}

export default function MusicPage({ toast, confirm }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(null);
  const [tab, setTab] = useState("all");
  const [addMood, setAddMood] = useState("calm");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const [current, setCurrent] = useState(null);   // track loaded in the player
  const [playing, setPlaying] = useState(false);
  const [pos, setPos] = useState(0);
  const [length, setLength] = useState(0);
  const fileRef = useRef(null);
  const audioRef = useRef(null);

  const load = useCallback(async () => {
    try {
      setData(await api("/api/music"));
      setFailed(null);
    } catch (e) {
      setFailed(e.message);
      toast("Could not load the music library", true);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const a = audioRef.current;
    return () => a?.pause();
  }, []);

  const moods = useMemo(() => {
    if (!data) return [];
    return (data.groups.untagged || []).length ? [...data.moods, "untagged"] : data.moods;
  }, [data]);

  const rows = useMemo(() => {
    if (!data) return [];
    const list = tab === "all" ? moods.flatMap((m) => data.groups[m] || []) : data.groups[tab] || [];
    const needle = q.trim().toLowerCase();
    return needle ? list.filter((t) => t.name.toLowerCase().includes(needle)) : list;
  }, [data, moods, tab, q]);

  const paged = usePaged(rows, 10, tab + "|" + q);

  const pickTab = (m) => {
    setTab(m);
    if (data?.moods.includes(m)) setAddMood(m);
  };

  const upload = async (files) => {
    if (!files?.length || busy) return;
    setBusy(true);
    for (const file of files) {
      try {
        const fd = new FormData();
        fd.append("mood", addMood);
        fd.append("file", file);
        const res = await fetch("/api/music/upload", { method: "POST", body: fd });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        toast(`Added ${file.name} to ${moodName(addMood)}`);
      } catch (e) {
        toast(`${file.name}: ${e.message}`, true);
      }
    }
    setBusy(false);
    load();
  };

  const stop = () => {
    const a = audioRef.current;
    if (a) {
      a.pause();
      a.removeAttribute("src");
      a.load();
    }
    setCurrent(null);
    setPlaying(false);
    setPos(0);
    setLength(0);
  };

  const remove = async (track) => {
    const ok = await confirm({
      title: "Remove this track?",
      message: `"${track.name}" will no longer be used for ${moodName(track.mood)} topics.`,
      detail: "It moves to assets/music/_removed/. The file is not deleted.",
      confirmLabel: "Remove track", tone: "danger",
    });
    if (!ok) return;
    try {
      await api("/api/music/delete", { rel: track.rel });
      if (current?.rel === track.rel) stop();
      toast(`Removed ${track.name}. It is kept in the _removed folder.`);
      load();
    } catch (e) {
      toast(e.message, true);
    }
  };

  const toggle = (track) => {
    const a = audioRef.current;
    if (!a) return;
    const fail = () => toast("Could not play this file", true);
    if (current?.rel === track.rel) {
      if (a.paused) a.play().catch(fail);
      else a.pause();
      return;
    }
    a.pause();
    a.src = `/api/music/play/${encodeURI(track.rel)}`;
    a.volume = 0.7;
    setCurrent(track);
    setPos(0);
    setLength(track.duration_sec || 0);
    a.play().catch(fail);
  };

  const seek = (value) => {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = value;
    setPos(value);
  };

  const pct = length > 0 ? Math.min(100, (pos / length) * 100) : 0;
  const total = data?.total ?? 0;
  const heading = tab === "all" ? "All tracks" : moodName(tab);

  return (
    <>
      <PageHeader
        title="Music"
        sub={data
          ? `${plural(total, "track")} in ${plural(data.moods.length, "mood")}. Each video picks a track from its topic's mood.`
          : "Each video picks a track from its topic's mood."}
      >
        <Search value={q} onChange={setQ} placeholder="Search tracks" />
      </PageHeader>

      {data && data.source !== "folder" && (
        <Banner tone="info" title="Videos are using generated music right now">
          These files are not picked up until the music source is switched to the library.
          <details className="more">
            <summary>Show details</summary>
            <div className="raw">settings.yaml: audio.source is "{data.source}", set it to "folder"</div>
          </details>
        </Banner>
      )}

      {data && (
        <Tabs
          label="Mood" value={tab} onChange={pickTab}
          options={[
            { value: "all", label: "All", count: total },
            ...moods.map((m) => ({ value: m, label: moodName(m), count: (data.groups[m] || []).length })),
          ]}
        />
      )}

      <div className="split">
        <section className="wide card" style={{ padding: "8px 8px 16px" }} aria-label={`${heading} tracks`}>
          <div className="rowf" style={{ padding: "12px 12px 6px" }}>
            <h2>{heading}</h2>
            {tab !== "all" && MOOD_INFO[tab] && (
              <span className="muted" style={{ fontSize: 13 }}>used for {MOOD_INFO[tab]} topics</span>
            )}
          </div>

          {!data && !failed && <SkeletonRows rows={6} />}

          {!data && failed && (
            <Empty icon="alert" title="The music library did not load"
                   action={<Btn size="sm" icon="refresh" onClick={load}>Try again</Btn>}>
              <details className="more">
                <summary>Show details</summary>
                <div className="raw">{failed}</div>
              </details>
            </Empty>
          )}

          {data && rows.length === 0 && (
            q.trim() ? (
              <Empty icon="search" title="No tracks match your search"
                     action={<Btn size="sm" onClick={() => setQ("")}>Clear search</Btn>} />
            ) : (
              <Empty icon="music" title={tab === "all" ? "No tracks yet" : `No ${moodName(tab)} tracks yet`}>
                Topics with this mood use generated music until you add a file.
              </Empty>
            )
          )}

          {data && rows.length > 0 && (
            <>
              <div className="scroll">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th style={{ width: 52 }}><span className="sr">Play</span></th>
                      <th>Track</th>
                      <th style={{ width: "34%" }}>Preview</th>
                      <th className="r">Length</th>
                      <th className="r">Size</th>
                      <th style={{ width: 52 }}><span className="sr">Actions</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {paged.slice.map((t) => {
                      const [title, ext] = splitName(t.name);
                      const loaded = current?.rel === t.rel;
                      const on = loaded && playing;
                      return (
                        <tr key={t.rel} className={loaded ? "sel" : ""}>
                          <td>
                            <Btn size="sm" kind={on ? "primary" : ""} icon={on ? "pause" : "play"}
                                 iconOnly={on ? `Pause ${title}` : `Play ${title}`}
                                 onClick={() => toggle(t)} />
                          </td>
                          <td>
                            <div className="t" style={{ overflowWrap: "anywhere" }}>{title}</div>
                            <div className="k rowf" style={{ gap: 6 }}>
                              <span>
                                {[ext, tab === "all" ? moodName(t.mood) : "", loaded ? (on ? "now playing" : "paused") : ""]
                                  .filter(Boolean).join(" · ")}
                              </span>
                              {t.synth && (
                                <Chip plain tone="info" style={{ height: 18, fontSize: 11 }}
                                      title="Made by the pipeline's own synthesiser">Generated</Chip>
                              )}
                            </div>
                          </td>
                          <td>
                            <div className={"wave" + (loaded ? " play" : "")} aria-hidden="true"
                                 style={loaded ? { "--p": pct + "%" } : undefined} />
                          </td>
                          <td className="r num">{clock(t.duration_sec) || <span className="faint">unknown</span>}</td>
                          <td className="r num muted">{(t.size_kb / 1024).toFixed(1)} MB</td>
                          <td>
                            <Btn size="sm" kind="ghost" icon="trash" iconOnly={`Remove ${title}`}
                                 onClick={() => remove(t)} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {rows.length > 10 ? (
                <Pager p={paged} noun="tracks" sizes={[10, 25]} style={{ padding: "14px 12px 0" }} />
              ) : (
                <div className="pager" style={{ padding: "14px 12px 0" }}>
                  <span>{plural(rows.length, "track")}</span>
                </div>
              )}
            </>
          )}
        </section>

        <aside className="rail">
          <section className="card" aria-label="Add tracks">
            <div className="card-head"><h2>Add tracks</h2></div>
            <div
              className={"drop" + (over ? " over" : "")}
              onDragOver={(e) => { e.preventDefault(); setOver(true); }}
              onDragLeave={() => setOver(false)}
              onDrop={(e) => { e.preventDefault(); setOver(false); upload([...e.dataTransfer.files]); }}
            >
              <div className="ico"><Icon name="upload" /></div>
              <b>{busy ? "Adding tracks" : "Drop audio files here"}</b>
              <span className="muted" style={{ fontSize: 13 }}>mp3, wav, m4a, aac, ogg or flac</span>
              <Btn size="sm" style={{ marginTop: 4 }} disabled={busy || !data}
                   onClick={() => fileRef.current?.click()}>
                Choose files
              </Btn>
              <input ref={fileRef} type="file" accept="audio/*" multiple hidden aria-label="Audio files to add"
                     onChange={(e) => { upload([...e.target.files]); e.target.value = ""; }} />
            </div>
            <label className="field" style={{ marginTop: 14 }}>
              Add to mood
              <select className="select" value={addMood} disabled={!data}
                      onChange={(e) => setAddMood(e.target.value)}>
                {(data?.moods || [addMood]).map((m) => <option key={m} value={m}>{moodName(m)}</option>)}
              </select>
            </label>
            <p className="faint" style={{ fontSize: 12.5, marginTop: 10 }}>
              Only use royalty-free, CC or public-domain music you have the rights to.
            </p>
          </section>

          <section className="card" aria-label="Moods">
            <div className="card-head"><h2>What each mood is for</h2></div>
            <dl className="kv stack" style={{ gap: 10 }}>
              {(data ? moods : Object.keys(MOOD_INFO).slice(0, 6)).map((m) => (
                <div key={m}>
                  <dt>{moodName(m)}</dt>
                  <dd className="muted">{MOOD_INFO[m] || "no description"}</dd>
                </div>
              ))}
            </dl>
          </section>
        </aside>
      </div>

      {current && (
        <section className="card rowf" aria-label="Player"
                 style={{ marginTop: "auto", gap: 16, background: "var(--raised)" }}>
          <Btn kind="primary" icon={playing ? "pause" : "play"} iconOnly={playing ? "Pause" : "Play"}
               onClick={() => toggle(current)} />
          <div style={{ flex: "0 1 260px", minWidth: 0 }}>
            <div style={{ fontWeight: 550, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {splitName(current.name)[0]}
            </div>
            <div className="muted" style={{ fontSize: 13 }}>{moodName(current.mood)}</div>
          </div>
          <span className="num muted">{clock(pos) || "0:00"}</span>
          <input className="seek" type="range" min={0} max={length || 0} step={0.1} value={Math.min(pos, length || 0)}
                 disabled={!length} aria-label="Position in track" aria-valuetext={`${clock(pos)} of ${clock(length)}`}
                 style={{ "--p": pct + "%" }} onChange={(e) => seek(Number(e.target.value))} />
          <span className="num muted">{clock(length)}</span>
          <Btn kind="ghost" icon="close" iconOnly="Close player" onClick={stop} />
        </section>
      )}

      <audio
        ref={audioRef} preload="none"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => { setPlaying(false); setPos(0); }}
        onTimeUpdate={(e) => setPos(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => { if (isFinite(e.currentTarget.duration)) setLength(e.currentTarget.duration); }}
      />
    </>
  );
}
