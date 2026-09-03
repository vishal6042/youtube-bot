import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import AgentNetwork from "./components/AgentNetwork.jsx";
import StatsRow from "./components/StatsRow.jsx";
import LaunchControl from "./components/LaunchControl.jsx";
import Analytics from "./components/Analytics.jsx";
import UploadControl from "./components/UploadControl.jsx";
import UploadLive from "./components/UploadLive.jsx";
import UploadQueue from "./components/UploadQueue.jsx";
import PlaylistCards from "./components/PlaylistCards.jsx";
import PlaylistList from "./components/PlaylistList.jsx";
import PlaylistDetail from "./components/PlaylistDetail.jsx";
import History from "./components/History.jsx";
import TopicCatalog from "./components/TopicCatalog.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Jobs from "./components/Jobs.jsx";
import Telemetry from "./components/Telemetry.jsx";
import FailureCenter from "./components/FailureCenter.jsx";
import Settings from "./components/Settings.jsx";
import UploadHistory from "./components/UploadHistory.jsx";
import MusicLibrary from "./components/MusicLibrary.jsx";
import TopicIdeas from "./components/TopicIdeas.jsx";
import MarkModal from "./components/MarkModal.jsx";
import VideoModal from "./components/VideoModal.jsx";
import ConfirmModal from "./components/ConfirmModal.jsx";

const MAX_TERM_LINES = 400;

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return <div className="clock">{now.toLocaleTimeString("en-GB")}</div>;
}

export default function App() {
  const [state, setState] = useState(null);
  const [online, setOnline] = useState(null);
  const [termLines, setTermLines] = useState(["agent idle. waiting for orders…"]);
  const [toasts, setToasts] = useState([]);
  const [modal, setModal] = useState(null);
  const [view, setViewRaw] = useState(null); // null = home, else a series key
  // Views ride on the browser history stack, so ◂ BACK (and the browser's own
  // back button) return to where you actually came from — Playlists → detail →
  // back lands on Playlists, not Mission.
  const navDepth = useRef(0);
  const setView = useCallback((v) => {
    setViewRaw((prev) => {
      if (v !== prev) {
        navDepth.current += 1;
        window.history.pushState({ view: v, depth: navDepth.current }, "");
      }
      return v;
    });
  }, []);
  const goBack = useCallback(() => {
    if (navDepth.current > 0) window.history.back();
    else setViewRaw(null);
  }, []);
  useEffect(() => {
    window.history.replaceState({ view: null, depth: 0 }, "");
    const onPop = (e) => {
      navDepth.current = e.state?.depth ?? 0;
      setViewRaw(e.state?.view ?? null);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const [pending, setPending] = useState(0); // in-flight mutations (drives progress UI)
  const [video, setVideo] = useState(null);  // topic being previewed in the player
  const [confirmState, setConfirmState] = useState(null);
  const confirmResolver = useRef(null);

  const logRef = useRef({ jobId: null, offset: 0 });
  const timerRef = useRef(null);
  const seededRef = useRef(false);

  // Promise-based confirm so callers keep reading like window.confirm did.
  const confirm = useCallback((opts) => new Promise((resolve) => {
    confirmResolver.current = resolve;
    setConfirmState(opts);
  }), []);

  // Same dialog, but resolves the typed string instead of a boolean.
  const promptText = useCallback((opts) => new Promise((resolve) => {
    confirmResolver.current = resolve;
    setConfirmState({ confirmLabel: "SAVE", ...opts, input: opts.input || {} });
  }), []);

  const resolveConfirm = useCallback((ok) => {
    setConfirmState(null);
    const r = confirmResolver.current;
    confirmResolver.current = null;
    r?.(ok);
  }, []);

  const toast = useCallback((msg, isErr = false) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, isErr }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);

  const pollLog = useCallback(async (jobId) => {
    if (logRef.current.jobId !== jobId) {
      logRef.current = { jobId, offset: 0 };
      setTermLines([]);
    }
    try {
      const r = await api(`/api/jobs/${jobId}/log?offset=${logRef.current.offset}`);
      if (r.lines.length) {
        logRef.current.offset = r.next;
        setTermLines((prev) => [...prev, ...r.lines].slice(-MAX_TERM_LINES));
      }
    } catch {
      /* transient */
    }
  }, []);

  const poll = useCallback(async () => {
    let busy = false;
    try {
      const s = await api("/api/state");
      setState(s);
      setOnline(true);
      busy = !!s.job;
      if (s.job) {
        seededRef.current = true;
        await pollLog(s.job.id);
      } else if (!seededRef.current) {
        // Idle at load: show the last job's log so the panel isn't empty.
        seededRef.current = true;
        const last = s.history[0];
        if (last?.log?.length) {
          setTermLines([
            `─── last job · ${last.label} · ${last.status.toUpperCase()} ───`,
            ...last.log.slice(-30),
          ]);
        }
      }
    } catch {
      setOnline(false);
    }
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(poll, busy ? 1500 : 3500);
  }, [pollLog]);

  useEffect(() => {
    poll();
    return () => clearTimeout(timerRef.current);
  }, [poll]);

  // ---- actions ----
  const renderTopics = async (keys, title) => {
    try {
      await api("/api/render", { keys });
      toast(`▶ Queued render: ${title || keys.join(", ")}`);
      poll();
    } catch (e) {
      toast(e.message, true);
    }
  };

  // Launch Control sends the exact keys it previewed, so what runs is what
  // the user saw — no re-selection at submit time.
  const renderBatch = async ({ keys, refresh, label }) => {
    try {
      await api("/api/render", { keys, refresh });
      toast(`▶ Queued ${keys.length} render${keys.length === 1 ? "" : "s"} (${label})`);
      poll();
    } catch (e) {
      toast(e.message, true);
    }
  };

  const cancelJob = async (jobId, queued = false) => {
    if (!queued && !await confirm({
      title: "Abort the running job?",
      message: "The current render stops immediately. Anything already exported is kept.",
      confirmLabel: "✕ ABORT JOB", tone: "danger",
    })) return;
    try {
      await api(`/api/jobs/${jobId}/cancel`, {});
      toast(queued ? "Removed from queue" : "Job aborted");
      poll();
    } catch (e) {
      toast(e.message, true);
    }
  };

  // Marking rewrites the upload log and regenerates UPLOAD_QUEUE.md, which
  // takes a beat — surface that instead of leaving the dialog looking frozen.
  const confirmMark = async (key, url) => {
    setPending((n) => n + 1);
    try {
      await api("/api/mark", { key, url });
      setModal(null);
      toast("✅ Marked uploaded — queue updated");
      await poll();
    } catch (e) {
      toast(e.message, true);
    } finally {
      setPending((n) => n - 1);
    }
  };

  const unmark = async (key, title) => {
    setPending((n) => n + 1);
    try {
      await api("/api/unmark", { key });
      toast(`↩ Unmarked ${title}`);
      await poll();
    } catch (e) {
      toast(e.message, true);
    } finally {
      setPending((n) => n - 1);
    }
  };

  const setPlaylistCreated = async (series, name, created = true) => {
    setPending((n) => n + 1);
    try {
      await api("/api/playlist-created", { series, created });
      toast(created
        ? `✅ ${name} marked as created on YouTube`
        : `↩ ${name} marked as not created`);
      await poll();
    } catch (e) {
      toast(e.message, true);
    } finally {
      setPending((n) => n - 1);
    }
  };

  const revertTopic = async (key, title) => {
    if (!await confirm({
      title: "Remove this topic?",
      message: `"${title}" goes back out of config/topics.yaml.`,
      detail: "It has never been rendered, so no video is lost.",
      confirmLabel: "✕ REMOVE", tone: "danger",
    })) return;
    setPending((n) => n + 1);
    try {
      await api("/api/topics/remove", { key });
      toast(`✕ Reverted ${title}`);
      await poll();
    } catch (e) {
      toast(e.message, true);
    } finally {
      setPending((n) => n - 1);
    }
  };

  const discardVideo = async (key, title) => {
    const reason = await promptText({
      title: "Discard this video?",
      message: `"${title}" leaves the upload queue without being recorded as uploaded.`,
      detail: "Its files move to export/_discarded/ — you can restore it from the "
            + "Discarded tab.",
      input: { label: "REASON (optional)", placeholder: "e.g. data was wrong" },
      confirmLabel: "🗑 DISCARD", tone: "danger",
    });
    if (reason === null) return;
    setPending((n) => n + 1);
    try {
      await api("/api/discard", { key, reason: reason.trim() });
      toast(`🗑 Discarded ${title}`);
      await poll();
    } catch (e) {
      toast(e.message, true);
    } finally {
      setPending((n) => n - 1);
    }
  };

  const restoreVideo = async (key, title) => {
    setPending((n) => n + 1);
    try {
      await api("/api/discard/restore", { key });
      toast(`↩ Restored ${title}`);
      await poll();
    } catch (e) {
      toast(e.message, true);
    } finally {
      setPending((n) => n - 1);
    }
  };

  /* The arrow stages a video for upload; nothing leaves the machine until the
     batch is run from Upload Control. So this needs no confirmation — the
     confirmation lives on the run, where it belongs. */
  const uploadVideo = async (item) => {
    try {
      await api("/api/upload/batch/add", { key: item.key });
      toast(`⬆ ${item.title} staged for upload`);
      await poll();
    } catch (e) {
      toast(e.message, true);
    }
  };

  const unstageVideo = async (item) => {
    try {
      await api("/api/upload/batch/remove", { key: item.key });
      toast(`Removed ${item.title} from the upload batch`);
      await poll();
    } catch (e) {
      toast(e.message, true);
    }
  };

  const clearUploadBatch = async () => {
    try {
      const r = await api("/api/upload/batch/clear", {});
      toast(r.removed ? `Cleared ${r.removed} finished upload(s)` : "Nothing to clear");
      await poll();
    } catch (e) {
      toast(e.message, true);
    }
  };

  const openFolder = async (path) => {
    if (!path) return;
    try {
      await api("/api/open", { path });
    } catch (e) {
      toast(e.message, true);
    }
  };

  const workingKey = state?.job?.current_key || null;
  const failures = state?.failures || [];
  const detailSeries = view && state ? state.series.find((s) => s.series === view) : null;
  const retryKeys = (keys) => renderTopics(keys, `retry ${keys.join(", ")}`);
  const addLink = async (key, title) => {
    const url = await promptText({
      title: "YouTube link",
      message: `Paste the link for "${title}".`,
      input: { label: "VIDEO URL", placeholder: "https://youtu.be/…" },
      confirmLabel: "SAVE LINK",
    });
    if (url === null) return;
    setPending((n) => n + 1);
    try {
      await api("/api/upload-link", { key, url: url.trim() });
      toast(url.trim() ? "✅ Link saved" : "↩ Link removed");
      await poll();
    } catch (e) {
      toast(e.message, true);
    } finally {
      setPending((n) => n - 1);
    }
  };

  const rowHandlers = {
    onMark: (key, title) => setModal({ key, title }),
    onOpen: openFolder,
    onRender: (key, title) => renderTopics([key], title),
    onLink: addLink,
    onWatch: (item) => setVideo(item),
  };

  return (
    <>
      <div className="bg-grid" aria-hidden="true" />
      {pending > 0 && <div className="top-progress" role="progressbar" aria-label="Working" />}

      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">◈</div>
          <div>
            <h1 onClick={() => setView(null)} style={{ cursor: "pointer" }}>DATA IN MOTION</h1>
            <div className="sub">MISSION CONTROL · UPLOAD PIPELINE</div>
          </div>
        </div>
        <div className="topbar-right">
          {state?.job && (
            <div className="topbar-job">
              ◉ {(state.job.stage || "starting").toUpperCase()} · {state.job.current_key || state.job.label}
            </div>
          )}
          <div className={"conn " + (online == null ? "" : online ? "on" : "off")}>
            <span className="dot" />
            <span>{online == null ? "CONNECTING" : online ? "LINK ACTIVE" : "LINK LOST"}</span>
          </div>
          <Clock />
        </div>
      </header>

      {state && (
        <div className="shell">
          <Sidebar
            view={view}
            setView={setView}
            failureCount={failures.length}
            counts={state.counts}
          />

          <main className="layout-col">
            {!view && (
              <>
                <StatsRow counts={state.counts} />

                <AgentNetwork
                  job={state.job}
                  queue={state.queue}
                  history={state.history}
                  onCancel={() => state.job && cancelJob(state.job.id)}
                />

                <UploadLive
                  batch={state.upload_batch || []}
                  run={state.upload_run || {}}
                  onOpen={() => setView("__upload")}
                  onClear={clearUploadBatch}
                />

                <div className="ops-grid">
                  <Jobs
                    job={state.job}
                    queue={state.queue}
                    history={state.history}
                    onAbort={() => state.job && cancelJob(state.job.id)}
                    onCancelQueued={(id) => cancelJob(id, true)}
                    onRetry={retryKeys}
                    onViewAll={() => setView("__history")}
                  />
                  <Telemetry
                    online={online}
                    job={state.job}
                    failures={failures}
                    history={state.history}
                    lines={termLines}
                  />
                </div>

                {failures.length > 0 && (
                  <FailureCenter failures={failures} onRetry={retryKeys} />
                )}

                <PlaylistList
                  series={state.series}
                  nextUp={state.next_up}
                  onOpenPlaylist={setView}
                  onViewAll={() => setView("__playlists")}
                  onPlaylistCreated={setPlaylistCreated}
                />
              </>
            )}

            {view === "__topics" && (
              <TopicCatalog
                onBack={goBack}
                workingKey={workingKey}
                onRender={(key, title) => renderTopics([key], title)}
                onOpen={openFolder}
                onWatch={rowHandlers.onWatch}
                promptText={promptText}
                toast={toast}
              />
            )}

            {view === "__playlists" && (
              <>
                <section className="panel">
                  <div className="detail-head">
                    <button className="btn back-btn" onClick={goBack}>◂ BACK</button>
                    <div>
                      <div className="pl-name">PLAYLISTS</div>
                      <div className="pl-series">
                        every series · tap a card to see its videos
                      </div>
                    </div>
                  </div>
                </section>
                <PlaylistCards
                  series={state.series}
                  nextUp={state.next_up}
                  onOpenPlaylist={setView}
                />
              </>
            )}

            {view === "__history" && (
              <>
                {failures.length > 0 && (
                  <FailureCenter failures={failures} onRetry={retryKeys} />
                )}
                <section className="panel">
                  <div className="detail-head">
                    <button className="btn back-btn" onClick={goBack}>◂ BACK</button>
                    <div>
                      <div className="pl-name">JOB HISTORY</div>
                      <div className="pl-series">
                        queued · running · finished jobs — click a row for its pipeline steps
                      </div>
                    </div>
                  </div>
                  <History
                    job={state.job}
                    queue={state.queue}
                    history={state.history}
                    limit={40}
                    expandable
                    onRetry={retryKeys}
                  />
                </section>
              </>
            )}

            {view === "__uploads" && (
              <UploadHistory
                onBack={goBack}
                onOpen={openFolder}
                onUnmark={unmark}
                onWatch={rowHandlers.onWatch}
                confirm={confirm}
                toast={toast}
              />
            )}

            {view === "__music" && (
              <MusicLibrary onBack={goBack} toast={toast} confirm={confirm} />
            )}

            {view === "__ideas" && (
              <TopicIdeas onBack={goBack} toast={toast} refresh={poll} />
            )}

            {view === "__launch" && (
              <LaunchControl
                series={state.series}
                onRenderBatch={renderBatch}
                onRevertTopic={revertTopic}
                onBack={goBack}
                onStarted={() => setView(null)}
                confirm={confirm}
                busy={!!state.job}
                pipelineVersion={
                  `${state.job?.current_key || "idle"}:${state.queue.length}:${state.history.length}`
                }
              />
            )}

            {view === "__upload" && (
              <>
                <UploadControl
                  onBack={goBack}
                  onStarted={() => setView(null)}
                  toast={toast}
                  confirm={confirm}
                />
                  <UploadQueue
                    items={state.next_up}
                    discarded={state.discarded || []}
                    customOrder={state.custom_order}
                    onMark={rowHandlers.onMark}
                    onOpen={openFolder}
                    onRender={rowHandlers.onRender}
                    onWatch={rowHandlers.onWatch}
                    onDiscard={discardVideo}
                    onRestore={restoreVideo}
                    onUpload={uploadVideo}
                    onUnstage={unstageVideo}
                    staged={(state.upload_batch || []).reduce(
                      (a, b) => ({ ...a, [b.key]: b }), {})}
                      onPlaylistCreated={setPlaylistCreated}
                    toast={toast}
                    refresh={poll}
                  />
              </>
            )}

            {view === "__analytics" && (
              <Analytics onBack={goBack} onWatch={rowHandlers.onWatch} toast={toast} />
            )}

            {view === "__settings" && (
              <Settings onBack={goBack} toast={toast} confirm={confirm} />
            )}

            {detailSeries && (
              <PlaylistDetail
                s={detailSeries}
                nextUp={state.next_up}
                workingKey={workingKey}
                onBack={goBack}
                onPlaylistCreated={setPlaylistCreated}
                {...rowHandlers}
              />
            )}
          </main>
        </div>
      )}

      <ConfirmModal state={confirmState} onResolve={resolveConfirm} />

      <VideoModal
        video={video}
        onClose={() => setVideo(null)}
        onOpenFolder={openFolder}
      />

      <MarkModal
        modal={modal}
        onClose={() => setModal(null)}
        onConfirm={confirmMark}
        busy={pending > 0}
      />

      <div className="toasts">
        {toasts.map((t) => (
          <div className={"toast" + (t.isErr ? " err" : "")} key={t.id}>{t.msg}</div>
        ))}
      </div>
    </>
  );
}
