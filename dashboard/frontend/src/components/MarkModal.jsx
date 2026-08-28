import { useEffect, useRef, useState } from "react";

export default function MarkModal({ modal, onClose, onConfirm, busy }) {
  const [url, setUrl] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    setUrl("");
    if (modal) inputRef.current?.focus();
  }, [modal]);

  if (!modal) return null;

  const confirm = () => !busy && onConfirm(modal.key, url.trim() || null);

  return (
    <div
      className="modal-back"
      onClick={(e) => e.target === e.currentTarget && !busy && onClose()}
    >
      <div className={"modal" + (busy ? " busy" : "")}>
        <div className="panel-title">MARK AS UPLOADED</div>
        <p className="modal-topic">{modal.title}  ({modal.key})</p>
        <label className="modal-label">
          YouTube URL <span className="muted">(optional)</span>
          <input
            ref={inputRef}
            type="url"
            placeholder="https://youtu.be/…"
            value={url}
            disabled={busy}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && confirm()}
          />
        </label>

        {busy && (
          <div className="modal-progress">
            <div className="mp-bar"><span /></div>
            <div className="mp-steps">
              Saving upload log · refreshing queue · rewriting UPLOAD_QUEUE.md
            </div>
          </div>
        )}

        <div className="modal-actions">
          <button className="btn" onClick={onClose} disabled={busy}>CANCEL</button>
          <button className="btn btn-primary" onClick={confirm} disabled={busy}>
            {busy ? <><span className="spinner" /> MARKING…</> : "✅ MARK UPLOADED"}
          </button>
        </div>
      </div>
    </div>
  );
}
