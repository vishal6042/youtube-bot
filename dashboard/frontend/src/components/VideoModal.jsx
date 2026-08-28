import { useEffect, useRef } from "react";

/* Watch a rendered video without leaving the dashboard. Portrait 1080x1920
   source, so the frame is sized tall-and-narrow to match. */
export default function VideoModal({ video, onClose, onOpenFolder }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!video) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [video, onClose]);

  if (!video) return null;

  return (
    <div
      className="vid-back"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="vid-modal">
        <div className="vid-head">
          <div>
            <div className="vid-title">{video.title}</div>
            <div className="vid-sub">
              {video.playlist || video.series}
              {video.duration_sec ? ` · ${Math.round(video.duration_sec)}s` : ""}
            </div>
          </div>
          <button className="vid-close" onClick={onClose} title="Close (Esc)">✕</button>
        </div>

        <video
          ref={ref}
          src={`/api/video/${video.key}`}
          controls
          autoPlay
          loop
          playsInline
          style={{ aspectRatio: "9 / 16" }}
        />

        <div className="vid-actions">
          {video.url && (
            <a className="btn btn-mini" href={video.url} target="_blank" rel="noopener noreferrer">
              ▶ OPEN ON YOUTUBE
            </a>
          )}
          {video.exported && onOpenFolder && (
            <button className="btn btn-mini" onClick={() => onOpenFolder(video.exported)}>
              📂 OPEN FOLDER
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
