import { useEffect } from "react";
import { Icon } from "../ui.jsx";

/* Watch a rendered video without leaving the dashboard. Portrait 1080x1920
   source, so the frame is sized tall-and-narrow to match. */
export default function VideoModal({ video, onClose, onOpenFolder }) {
  useEffect(() => {
    if (!video) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [video, onClose]);

  if (!video) return null;

  return (
    <div
      className="modal-back"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="modal vid-modal" role="dialog" aria-modal="true" aria-label={video.title}>
        <div className="rowf" style={{ flexWrap: "nowrap", marginBottom: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <b>{video.title}</b>
            <div className="muted" style={{ fontSize: 13 }}>
              {video.playlist || video.series}
              {video.duration_sec ? ` · ${Math.round(video.duration_sec)}s` : ""}
            </div>
          </div>
          <button type="button" className="btn icon sm ghost" onClick={onClose} aria-label="Close" title="Close (Esc)">
            <Icon name="close" />
          </button>
        </div>

        <video
          src={`/api/video/${video.key}`}
          controls
          autoPlay
          loop
          playsInline
          style={{ aspectRatio: "9 / 16" }}
        />

        {(video.url || (video.exported && onOpenFolder)) && (
          <div className="rowf" style={{ marginTop: 12 }}>
            {video.url && (
              <a className="btn sm" href={video.url} target="_blank" rel="noopener noreferrer">
                <Icon name="external" /> Open on YouTube
              </a>
            )}
            {video.exported && onOpenFolder && (
              <button type="button" className="btn sm" onClick={() => onOpenFolder(video.exported)}>
                <Icon name="folder" /> Open folder
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
