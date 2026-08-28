import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const MOOD_INFO = {
  calm: "population, life, people",
  hopeful: "science, tech, energy, innovation",
  reflective: "CO₂, military, migration",
  majestic: "GDP, exports, economy",
  serene: "travel, nature, food",
  lofi: "developers, phones, internet",
  untagged: "used as a fallback for any mood",
};

function fmtDur(s) {
  if (!s) return "—";
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.round(s % 60)).padStart(2, "0")}`;
}

export default function MusicLibrary({ onBack, toast, confirm }) {
  const [data, setData] = useState(null);
  const [mood, setMood] = useState("calm");
  const [busy, setBusy] = useState(false);
  const [playing, setPlaying] = useState(null);
  const fileRef = useRef(null);
  const audioRef = useRef(null);

  const load = useCallback(async () => {
    try {
      setData(await api("/api/music"));
    } catch (e) {
      toast(e.message, true);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => () => audioRef.current?.pause(), []);

  const upload = async (files) => {
    if (!files?.length) return;
    setBusy(true);
    for (const file of files) {
      try {
        const fd = new FormData();
        fd.append("mood", mood);
        fd.append("file", file);
        const res = await fetch("/api/music/upload", { method: "POST", body: fd });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        toast(`🎵 Added ${file.name} to ${mood}`);
      } catch (e) {
        toast(`${file.name}: ${e.message}`, true);
      }
    }
    setBusy(false);
    load();
  };

  const remove = async (track) => {
    const ok = await confirm({
      title: "Remove this track?",
      message: `"${track.name}" will no longer be used for ${track.mood} topics.`,
      detail: "It moves to assets/music/_removed/ — the file is not deleted.",
      confirmLabel: "✕ REMOVE TRACK", tone: "danger",
    });
    if (!ok) return;
    try {
      await api("/api/music/delete", { rel: track.rel });
      toast(`↩ Moved ${track.name} to _removed/`);
      load();
    } catch (e) {
      toast(e.message, true);
    }
  };

  const play = (track) => {
    if (playing === track.rel) {
      audioRef.current?.pause();
      setPlaying(null);
      return;
    }
    audioRef.current?.pause();
    const a = new Audio(`/api/music/play/${encodeURI(track.rel)}`);
    a.volume = 0.7;
    a.play().catch(() => toast("Could not play this file", true));
    a.onended = () => setPlaying(null);
    audioRef.current = a;
    setPlaying(track.rel);
  };

  if (!data) {
    return (
      <section className="panel detail">
        <div className="detail-head">
          <button className="btn back-btn" onClick={onBack}>◂ BACK</button>
          <div className="pl-name">MUSIC LIBRARY</div>
        </div>
        <div className="empty">Loading…</div>
      </section>
    );
  }

  const moods = [...data.moods, "untagged"];

  return (
    <>
      <section className="panel">
        <div className="detail-head">
          <button className="btn back-btn" onClick={onBack}>◂ BACK</button>
          <div>
            <div className="pl-name">MUSIC LIBRARY</div>
            <div className="pl-series">
              tracks in assets/music · matched to topics by mood
              {data.source === "folder"
                ? " · pipeline is using these files"
                : " · pipeline is currently synthesizing music (settings.yaml → audio.source)"}
            </div>
          </div>
          <div className="uq-stats">
            <div className="uq-stat"><b>{data.total}</b><span>Tracks</span></div>
          </div>
        </div>

        <div
          className={"mus-drop" + (busy ? " busy" : "")}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); upload([...e.dataTransfer.files]); }}
        >
          <div className="mus-drop-main">
            <span className="mus-drop-icon">🎵</span>
            <div>
              <div className="mus-drop-title">
                {busy ? "Uploading…" : "Drop audio files here, or browse"}
              </div>
              <div className="lc-hint">
                mp3 · wav · m4a · aac · ogg · flac — use only royalty-free / CC /
                public-domain tracks you have the rights to.
              </div>
            </div>
          </div>
          <div className="mus-drop-actions">
            <label className="lc-field mus-mood-pick">
              <span className="set-label">ADD TO MOOD</span>
              <select value={mood} onChange={(e) => setMood(e.target.value)}>
                {data.moods.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </label>
            <button className="btn btn-primary" disabled={busy}
                    onClick={() => fileRef.current?.click()}>
              ⬆ CHOOSE FILES
            </button>
            <input ref={fileRef} type="file" accept="audio/*" multiple hidden
                   onChange={(e) => { upload([...e.target.files]); e.target.value = ""; }} />
          </div>
        </div>
      </section>

      {moods.map((m) => {
        const tracks = data.groups[m] || [];
        if (!tracks.length && m === "untagged") return null;
        return (
          <section className="panel" key={m}>
            <div className="panel-title">
              {m.toUpperCase()} <span className="muted">— {MOOD_INFO[m]}</span>
              <span className="mus-count">{tracks.length} track{tracks.length === 1 ? "" : "s"}</span>
            </div>
            {!tracks.length && (
              <div className="empty">
                No files — topics with this mood fall back to the synthesized theme.
              </div>
            )}
            <div className="mus-rows">
              {tracks.map((t) => (
                <div className="mus-row" key={t.rel}>
                  <button className="btn btn-mini mus-play" onClick={() => play(t)}
                          title={playing === t.rel ? "Stop" : "Preview"}>
                    {playing === t.rel ? "■" : "▶"}
                  </button>
                  <span className="mus-name">
                    {t.name}
                    {t.synth && <span className="chip chip-rendered mus-tag">synth</span>}
                  </span>
                  <span className="mus-dur">{fmtDur(t.duration_sec)}</span>
                  <span className="mus-size">{t.size_kb} KB</span>
                  <button className="btn btn-mini mus-del" onClick={() => remove(t)}
                          title="Move to _removed/">✕</button>
                </div>
              ))}
            </div>
          </section>
        );
      })}
    </>
  );
}
