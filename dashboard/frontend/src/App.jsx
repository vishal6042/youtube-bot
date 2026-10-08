import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import Overview from "./components/Overview.jsx";
import IdeasPage from "./components/IdeasPage.jsx";
import TopicsPage from "./components/TopicsPage.jsx";
import RenderPage from "./components/RenderPage.jsx";
import JobsPage from "./components/JobsPage.jsx";
import UploadPage from "./components/UploadPage.jsx";
import PublishedPage from "./components/PublishedPage.jsx";
import PlaylistsPage from "./components/PlaylistsPage.jsx";
import AnalyticsPage from "./components/AnalyticsPage.jsx";
import MusicPage from "./components/MusicPage.jsx";
import SettingsPage from "./components/SettingsPage.jsx";
import Sidebar from "./components/Sidebar.jsx";
import CommandPalette from "./components/CommandPalette.jsx";
import MarkModal from "./components/MarkModal.jsx";
import VideoModal from "./components/VideoModal.jsx";
import ConfirmModal from "./components/ConfirmModal.jsx";
import { SkeletonRows } from "./ui.jsx";

const MAX_TERM_LINES = 400;

export default function App() {
  const [state, setState] = useState(null);
  const [online, setOnline] = useState(null);
  const [termLines, setTermLines] = useState([]);
  const [toasts, setToasts] = useState([]);
  const [modal, setModal] = useState(null);
  const [view, setViewRaw] = useState(null); // null = Overview, else a "__screen" id
  const [plSel, setPlSel] = useState(null);       // playlist open on the Playlists screen
  const [topicQuery, setTopicQuery] = useState(""); // handed to Topics by global search
  const [palette, setPalette] = useState(false);
  const [ideasCount, setIdeasCount] = useState(null);
  // Views ride on the browser history stack, so the browser's back button
  // returns to the screen you actually came from.
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
  useEffect(() => {
    window.history.replaceState({ view: null, depth: 0 }, "");
    const onPop = (e) => {
      navDepth.current = e.state?.depth ?? 0;
      setViewRaw(e.state?.view ?? null);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
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
    setConfirmState({ confirmLabel: "Save", ...opts, input: opts.input || {} });
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
      toast(`Render queued: ${title || keys.join(", ")}`);
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
      toast(`${keys.length} render${keys.length === 1 ? "" : "s"} queued (${label})`);
      poll();
    } catch (e) {
      toast(e.message, true);
    }
  };

  const cancelJob = async (jobId, queued = false) => {
    if (!queued && !await confirm({
      title: "Abort the running job?",
      message: "The current render stops immediately. Anything already exported is kept.",
      confirmLabel: "Abort job", cancelLabel: "Keep running", tone: "danger",
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
      toast("Marked as uploaded");
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
      toast(`${title} is back in the upload queue`);
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
        ? `${name} marked as created on YouTube`
        : `${name} marked as not created`);
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
      confirmLabel: "Remove topic", tone: "danger",
    })) return;
    setPending((n) => n + 1);
    try {
      await api("/api/topics/remove", { key });
      toast(`Removed ${title}`);
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
      detail: "Its files are kept. You can restore it from the Discarded tab.",
      input: { label: "Reason (optional)", placeholder: "e.g. data was wrong" },
      confirmLabel: "Discard", tone: "danger",
    });
    if (reason === null) return;
    setPending((n) => n + 1);
    try {
      await api("/api/discard", { key, reason: reason.trim() });
      toast(`Discarded ${title}`);
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
      toast(`Restored ${title}`);
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
      toast(`${item.title} added to today's batch`);
      await poll();
    } catch (e) {
      toast(e.message, true);
    }
  };

  const unstageVideo = async (item) => {
    try {
      await api("/api/upload/batch/remove", { key: item.key });
      toast(`${item.title} removed from today's batch`);
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

  // Several topics from the Topics screen: one job each, as /api/render does.
  const renderMany = async (keys) => {
    try {
      await api("/api/render", { keys });
      toast(`${keys.length} render${keys.length === 1 ? "" : "s"} queued`);
      setView("__launch");
      poll();
    } catch (e) {
      toast(e.message, true);
    }
  };

  const openPlaylist = (series) => {
    setPlSel(series);
    setView("__playlists");
  };

  // Build Next's count for the sidebar; refreshed when the catalogue changes.
  const topicTotal = state?.counts?.total;
  useEffect(() => {
    if (topicTotal == null) return;
    api("/api/ideas")
      .then((r) => setIdeasCount(r.ideas.filter((i) => i.state === "ready").length))
      .catch(() => {});
  }, [topicTotal]);

  const workingKey = state?.job?.current_key || null;
  const failures = state?.failures || [];
  const retryKeys = (keys) => renderTopics(keys, `retry ${keys.join(", ")}`);
  const addLink = async (key, title) => {
    const url = await promptText({
      title: "YouTube link",
      message: `Paste the link for "${title}".`,
      input: { label: "Video link", placeholder: "https://youtu.be/…" },
      confirmLabel: "Save link",
    });
    if (url === null) return;
    setPending((n) => n + 1);
    try {
      await api("/api/upload-link", { key, url: url.trim() });
      toast(url.trim() ? "Link saved" : "Link removed");
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

  const abortJob = () => state.job && cancelJob(state.job.id);
  // Jobs only carry topic keys; this lets the job views show real titles.
  const titles = {};
  for (const sr of state?.series || []) for (const it of sr.items) titles[it.key] = it.title;
  const cancelQueued = (id) => cancelJob(id, true);
  const navCounts = state
    ? { ...state.counts, ideas: ideasCount, failures: failures.length }
    : {};

  return (
    <div className="app">
      {pending > 0 && <div className="top-progress" role="progressbar" aria-label="Working" />}

      <Sidebar
        view={view}
        setView={setView}
        counts={navCounts}
        online={online}
        running={!!state?.job}
      />

      {/* Keyed by view so each screen plays its enter animation once. */}
      <main className="main rise" key={view ?? "home"}>
        {!state && <SkeletonRows rows={8} />}

        {state && !view && (
          <Overview
            state={state}
            ideasCount={ideasCount}
            lines={termLines}
            titles={titles}
            setView={setView}
            onOpenSearch={() => setPalette(true)}
            onCancel={abortJob}
            onCancelQueued={cancelQueued}
          />
        )}

        {state && view === "__ideas" && (
          <IdeasPage toast={toast} refresh={poll} onOpenTopics={() => setView("__topics")} />
        )}

        {state && view === "__topics" && (
          <TopicsPage
            workingKey={workingKey}
            onRender={(key, title) => renderTopics([key], title)}
            onRenderMany={renderMany}
            onOpen={openFolder}
            onWatch={rowHandlers.onWatch}
            onRemove={revertTopic}
            onBrowseIdeas={() => setView("__ideas")}
            promptText={promptText}
            confirm={confirm}
            toast={toast}
            initialQuery={topicQuery}
          />
        )}

        {state && view === "__launch" && (
          <RenderPage
            series={state.series}
            job={state.job}
            queue={state.queue}
            lines={termLines}
            onRenderBatch={renderBatch}
            onRevertTopic={revertTopic}
            onCancel={abortJob}
            onCancelQueued={cancelQueued}
            confirm={confirm}
            busy={!!state.job}
            pipelineVersion={
              `${state.job?.current_key || "idle"}:${state.queue.length}:${state.history.length}`
            }
          />
        )}

        {state && view === "__history" && (
          <JobsPage
            job={state.job}
            queue={state.queue}
            history={state.history}
            failures={failures}
            lines={termLines}
            titles={titles}
            onRetry={retryKeys}
            onCancel={abortJob}
            onCancelQueued={cancelQueued}
            onNewRender={() => setView("__launch")}
          />
        )}

        {state && view === "__upload" && (
          <UploadPage
            items={state.next_up}
            discarded={state.discarded || []}
            customOrder={state.custom_order}
            staged={(state.upload_batch || []).reduce((a, b) => ({ ...a, [b.key]: b }), {})}
            batch={state.upload_batch || []}
            run={state.upload_run || {}}
            quota={state.upload_quota}
            onMark={rowHandlers.onMark}
            onOpen={openFolder}
            onRender={rowHandlers.onRender}
            onWatch={rowHandlers.onWatch}
            onDiscard={discardVideo}
            onRestore={restoreVideo}
            onUpload={uploadVideo}
            onUnstage={unstageVideo}
            onClearBatch={clearUploadBatch}
            onPlaylistCreated={setPlaylistCreated}
            confirm={confirm}
            toast={toast}
            refresh={poll}
          />
        )}

        {state && view === "__uploads" && (
          <PublishedPage
            onOpen={openFolder}
            onUnmark={unmark}
            onWatch={rowHandlers.onWatch}
            onLink={addLink}
            confirm={confirm}
            toast={toast}
          />
        )}

        {state && view === "__playlists" && (
          <PlaylistsPage
            series={state.series}
            nextUp={state.next_up}
            workingKey={workingKey}
            selected={plSel}
            onSelect={setPlSel}
            onPlaylistCreated={setPlaylistCreated}
            {...rowHandlers}
          />
        )}

        {state && view === "__analytics" && (
          <AnalyticsPage onWatch={rowHandlers.onWatch} toast={toast} />
        )}

        {state && view === "__music" && <MusicPage toast={toast} confirm={confirm} />}

        {state && view === "__settings" && <SettingsPage toast={toast} confirm={confirm} />}
      </main>

      <CommandPalette
        open={palette}
        onClose={() => setPalette(false)}
        onGo={setView}
        onTopic={(t) => {
          setTopicQuery(t.title);
          setView("__topics");
        }}
      />

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

      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div className={"toast" + (t.isErr ? " err" : "")} key={t.id}>{t.msg}</div>
        ))}
      </div>
    </div>
  );
}
