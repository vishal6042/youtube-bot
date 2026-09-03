import { useCallback, useEffect, useRef, useState } from "react";
import Retention from "./Retention.jsx";
import YouTubeSync from "./YouTubeSync.jsx";
import { api } from "../api.js";

function ImageCard({ img, onUpload, busy }) {
  const inputRef = useRef(null);
  const [bust, setBust] = useState(0);

  const pick = (e) => {
    const file = e.target.files?.[0];
    if (file) onUpload(img.name, file, () => setBust(Date.now()));
    e.target.value = "";
  };

  return (
    <div className="img-card">
      <div className="img-frame">
        <img src={`/api/brand/${img.name}?t=${bust}`} alt={img.name} loading="lazy" />
      </div>
      <div className="img-meta">
        <div className="img-role">{img.role}</div>
        <div className="img-name">{img.name}</div>
        <div className="img-facts">
          <span>{img.dimensions || "—"}</span>
          <span className="pd-dot">·</span>
          <span>{img.size_kb} KB</span>
        </div>
        <div className="img-rec">Recommended: {img.recommended}</div>
        <div className="img-mod">Updated {(img.modified || "").replace("T", " ")}</div>
        <button
          className="btn btn-mini"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          ⬆ REPLACE
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          hidden
          onChange={pick}
        />
      </div>
    </div>
  );
}

export default function Settings({ onBack, toast, confirm }) {
  const [data, setData] = useState(null);
  const [channel, setChannel] = useState({ description: "", tagline: "" });
  const [playlists, setPlaylists] = useState({});
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api("/api/settings");
      setData(r);
      setChannel(r.channel || { description: "", tagline: "" });
      setPlaylists(r.playlists || {});
      setDirty(false);
    } catch (e) {
      toast(e.message, true);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      await api("/api/settings", { channel, playlists });
      toast("✅ Settings saved");
      setDirty(false);
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(false);
  };

  const upload = async (name, file, done) => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("name", name);
      fd.append("file", file);
      const res = await fetch("/api/brand/upload", { method: "POST", body: fd });
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      toast(`✅ Replaced ${name} (previous version backed up)`);
      done?.();
      load();
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(false);
  };

  if (!data) {
    return (
      <section className="panel detail">
        <div className="detail-head">
          <button className="btn back-btn" onClick={onBack}>◂ BACK</button>
          <div className="pl-name">SETTINGS</div>
        </div>
        <div className="empty">Loading…</div>
      </section>
    );
  }

  const setPl = (series, field, value) => {
    setPlaylists((p) => ({ ...p, [series]: { ...p[series], [field]: value } }));
    setDirty(true);
  };

  return (
    <>
      <section className="panel">
        <div className="detail-head">
          <button className="btn back-btn" onClick={onBack}>◂ BACK</button>
          <div>
            <div className="pl-name">SETTINGS</div>
            <div className="pl-series">channel copy, playlist descriptions and brand assets</div>
          </div>
          <button
            className="btn btn-primary save-btn"
            disabled={!dirty || busy}
            onClick={save}
          >
            {dirty ? "💾 SAVE CHANGES" : "✓ SAVED"}
          </button>
        </div>
      </section>

      <YouTubeSync toast={toast} confirm={confirm} />

      <section className="panel">
        <div className="panel-title">CHANNEL</div>
        <label className="set-field">
          <span className="set-label">TAGLINE <span className="muted">— handle bios, other platforms</span></span>
          <input
            type="text"
            value={channel.tagline || ""}
            onChange={(e) => { setChannel({ ...channel, tagline: e.target.value }); setDirty(true); }}
          />
        </label>
        <label className="set-field">
          <span className="set-label">
            ABOUT DESCRIPTION
            <span className="muted"> — {(channel.description || "").length} chars (YouTube limit 1000)</span>
          </span>
          <textarea
            rows={12}
            value={channel.description || ""}
            onChange={(e) => { setChannel({ ...channel, description: e.target.value }); setDirty(true); }}
          />
        </label>
      </section>

      <section className="panel">
        <div className="panel-title">PLAYLIST DESCRIPTIONS</div>
        <div className="set-playlists">
          {Object.entries(playlists).map(([series, p]) => (
            <div className="set-pl" key={series}>
              <div className="set-pl-head">
                <input
                  className="set-pl-name"
                  type="text"
                  value={p.name || ""}
                  onChange={(e) => setPl(series, "name", e.target.value)}
                />
                <span className="pl-series">{series}</span>
                <span className="set-count muted">{(p.description || "").length} chars</span>
              </div>
              <label className="set-created">
                <input
                  type="checkbox"
                  checked={p.created !== false}
                  onChange={(e) => {
                    setPlaylists((prev) => ({
                      ...prev,
                      [series]: { ...prev[series], created: e.target.checked },
                    }));
                    setDirty(true);
                  }}
                />
                <span>Playlist exists on YouTube</span>
              </label>
              <textarea
                rows={5}
                placeholder="Description to paste on the YouTube playlist…"
                value={p.description || ""}
                onChange={(e) => setPl(series, "description", e.target.value)}
              />
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-title">BRAND IMAGES <span className="muted">— replacing keeps a backup</span></div>
        <div className="img-grid">
          {data.images.map((img) => (
            <ImageCard key={img.name} img={img} onUpload={upload} busy={busy} />
          ))}
        </div>
        {data.docs?.length > 0 && (
          <div className="set-docs">
            <span className="muted">Reference copy files:</span>{" "}
            {data.docs.map((d) => `${d.name} (${d.size_kb} KB)`).join(" · ")}
          </div>
        )}
      </section>
      <Retention toast={toast} confirm={confirm} />
    </>
  );
}
