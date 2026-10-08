import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { Btn, Chip, Empty, PageHeader, SkeletonRows, Tabs } from "../ui.jsx";
import ChannelTab from "./settings/ChannelTab.jsx";
import PlaylistsTab from "./settings/PlaylistsTab.jsx";
import BrandTab from "./settings/BrandTab.jsx";
import StorageTab from "./settings/StorageTab.jsx";
import "../screens/library.css";

export default function SettingsPage({ toast, confirm }) {
  const [tab, setTab] = useState("channel");
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(null);
  const [channel, setChannel] = useState({ description: "", tagline: "" });
  const [playlists, setPlaylists] = useState({});
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  // YouTube state lives here so a sync result survives switching tabs.
  const [stats, setStats] = useState(null);     // stored snapshot, costs no quota
  const [sync, setSync] = useState(null);       // live diff after a pull
  const [syncError, setSyncError] = useState(null);
  const [auth, setAuth] = useState(null);
  const [ytBusy, setYtBusy] = useState(false);
  const [retention, setRetention] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await api("/api/settings");
      setData(r);
      setChannel(r.channel || { description: "", tagline: "" });
      setPlaylists(r.playlists || {});
      setDirty(false);
      setFailed(null);
    } catch (e) {
      setFailed(e.message);
      toast("Could not load settings", true);
    }
  }, [toast]);

  const loadStats = useCallback(async () => {
    try { setStats(await api("/api/yt/stats")); } catch { /* database down: the card still renders */ }
  }, []);

  const loadRetention = useCallback(async () => {
    try {
      setRetention(await api("/api/retention"));
    } catch (e) {
      setRetention({ available: false, reason: e.message });
    }
  }, []);

  useEffect(() => {
    load();
    loadStats();
    loadRetention();
    api("/api/upload/auth").then(setAuth).catch(() => {});
  }, [load, loadStats, loadRetention]);

  const save = async () => {
    setBusy(true);
    try {
      await api("/api/settings", { channel, playlists });
      toast("Settings saved");
      await load();
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(false);
  };

  const discard = async () => {
    const ok = await confirm({
      title: "Discard your changes?",
      message: "The channel text and playlists go back to what was last saved.",
      confirmLabel: "Discard changes", cancelLabel: "Keep editing", tone: "danger",
    });
    if (ok) load();
  };

  const editChannel = (field, value) => {
    setChannel((c) => ({ ...c, [field]: value }));
    setDirty(true);
  };

  const editPlaylist = (series, field, value) => {
    setPlaylists((p) => ({ ...p, [series]: { ...p[series], [field]: value } }));
    setDirty(true);
  };

  const uploadImage = async (name, file, done) => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("name", name);
      fd.append("file", file);
      const res = await fetch("/api/brand/upload", { method: "POST", body: fd });
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      const r = await res.json();
      toast(`Replaced ${name}. The previous version was backed up.`);
      // Only the image list is refreshed, so unsaved text edits are not lost.
      if (r.image) {
        setData((d) => ({ ...d, images: d.images.map((i) => (i.name === r.image.name ? r.image : i)) }));
      }
      done?.();
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(false);
  };

  const pull = async () => {
    setYtBusy(true);
    setSyncError(null);
    try {
      const r = await api("/api/yt/sync", {});
      setSync(r);
      loadStats();
      if (r.adopted?.length) {
        toast(`Synced. Updated your local copy from YouTube: ${r.adopted.join(", ")}`);
        // The server rewrote the saved text; refresh unless that would wipe edits.
        if (!dirty) load();
      } else {
        toast(`Synced from YouTube (${r.units_spent} quota units)`);
      }
    } catch (e) {
      setSyncError(e.message);
      toast("Could not sync with YouTube", true);
    }
    setYtBusy(false);
  };

  const pushables = sync ? sync.playlists.filter((p) => p.found && p.differs) : [];
  const channelDiffers = !!sync?.channel?.differs;

  const push = async () => {
    const items = [];
    if (channelDiffers) items.push({ title: "Channel description", meta: "About page" });
    pushables.forEach((p) => items.push({
      title: p.name,
      meta: p.remote_title !== p.name ? `renamed from "${p.remote_title}"` : "description",
    }));
    const ok = await confirm({
      title: "Send these edits to YouTube?",
      message: `${items.length} item${items.length === 1 ? "" : "s"} will be updated on the `
             + "live channel (50 quota units each). This changes what viewers see.",
      items,
      confirmLabel: "Send to YouTube",
      tone: "danger",
    });
    if (!ok) return;
    setYtBusy(true);
    try {
      const r = await api("/api/yt/push", { channel: channelDiffers, playlists: pushables.map((p) => p.series) });
      if (r.errors?.length) toast(`Some edits were not sent: ${r.errors.join(" · ")}`, true);
      else toast(`Sent to YouTube: ${r.applied.join(", ")}`);
      await pull();
    } catch (e) {
      toast(e.message, true);
    }
    setYtBusy(false);
  };

  const count = Object.keys(playlists).length;
  const saveBar = { dirty, busy, onSave: save, onDiscard: discard };

  return (
    <>
      <PageHeader title="Settings" sub="Channel text, playlists, brand images and disk space">
        {dirty && <Chip tone="warn">Unsaved changes</Chip>}
      </PageHeader>

      <Tabs
        label="Settings sections" value={tab} onChange={setTab}
        options={[
          { value: "channel", label: "YouTube and channel" },
          { value: "playlists", label: "Playlists", count: data ? count : undefined },
          { value: "brand", label: "Brand images" },
          { value: "storage", label: "Storage" },
        ]}
      />

      {!data && tab !== "storage" && (
        <section className="card" aria-label="Settings">
          {failed ? (
            <Empty icon="alert" title="Settings did not load"
                   action={<Btn size="sm" icon="refresh" onClick={load}>Try again</Btn>}>
              <details className="more">
                <summary>Show details</summary>
                <div className="raw">{failed}</div>
              </details>
            </Empty>
          ) : <SkeletonRows rows={5} />}
        </section>
      )}

      {data && tab === "channel" && (
        <ChannelTab
          data={data} channel={channel} playlists={playlists} onEdit={editChannel} saveBar={saveBar}
          stats={stats} sync={sync} syncError={syncError} auth={auth} ytBusy={ytBusy}
          channelDiffers={channelDiffers} pushables={pushables} onPull={pull} onPush={push}
          retention={retention} onTab={setTab}
        />
      )}
      {data && tab === "playlists" && (
        <PlaylistsTab playlists={playlists} onEdit={editPlaylist} saveBar={saveBar} />
      )}
      {data && tab === "brand" && (
        <BrandTab images={data.images || []} docs={data.docs || []} busy={busy} onUpload={uploadImage} />
      )}
      {tab === "storage" && (
        <StorageTab data={retention} reload={loadRetention} toast={toast} confirm={confirm} />
      )}
    </>
  );
}
