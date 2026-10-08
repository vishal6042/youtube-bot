import { useEffect, useRef, useState } from "react";

export default function MarkModal({ modal, onClose, onConfirm, busy }) {
  const [url, setUrl] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    setUrl("");
    if (modal) inputRef.current?.focus();
  }, [modal]);

  useEffect(() => {
    if (!modal) return;
    const onKey = (e) => e.key === "Escape" && !busy && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [modal, busy, onClose]);

  if (!modal) return null;

  const confirm = () => !busy && onConfirm(modal.key, url.trim() || null);

  return (
    <div
      className="modal-back"
      onClick={(e) => e.target === e.currentTarget && !busy && onClose()}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-label="Mark as uploaded">
        <h2>Mark as uploaded</h2>
        <p>
          {modal.title} <span className="num faint" style={{ fontSize: 12 }}>{modal.key}</span>
        </p>
        <label className="field">
          YouTube link (optional)
          <input
            ref={inputRef}
            className="input"
            type="url"
            placeholder="https://youtu.be/…"
            value={url}
            disabled={busy}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && confirm()}
          />
        </label>

        <div className="modal-actions">
          <button type="button" className="btn ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="button" className="btn primary" onClick={confirm} disabled={busy}>
            {busy ? <><span className="spin" /> Saving</> : "Mark as uploaded"}
          </button>
        </div>
      </div>
    </div>
  );
}
