import { useEffect, useRef, useState } from "react";

/* Themed replacement for window.confirm. Driven by App's `confirm()` helper,
   which returns a promise so callers can still `await` a decision. */
export default function ConfirmModal({ state, onResolve }) {
  const okRef = useRef(null);
  const inputRef = useRef(null);
  const [value, setValue] = useState("");

  useEffect(() => {
    if (!state) return;
    setValue(state.input?.initial || "");
    // A prompt wants the caret in the field; a plain confirm wants the button.
    (state.input ? inputRef.current : okRef.current)?.focus();
    const onKey = (e) => {
      if (e.key === "Escape") onResolve(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state, onResolve]);

  if (!state) return null;
  const {
    title = "Are you sure?",
    message,
    detail,
    items,
    confirmLabel = "CONFIRM",
    cancelLabel = "CANCEL",
    tone = "primary",   // primary | danger
    input,              // { label, placeholder, initial } -> resolves to a string
  } = state;

  // Confirm resolves true/false; prompt resolves the string (or null).
  const accept = () => onResolve(input ? value.trim() : true);

  return (
    <div
      className="modal-back"
      onClick={(e) => e.target === e.currentTarget && onResolve(null)}
    >
      <div className={"modal confirm-modal " + tone}>
        <div className="confirm-title">{title}</div>
        {message && <p className="confirm-msg">{message}</p>}

        {items?.length > 0 && (
          <ol className="confirm-items">
            {items.map((it, i) => (
              <li key={i}>
                <span className="confirm-num">{String(i + 1).padStart(2, "0")}</span>
                <span className="confirm-item-main">
                  <b>{it.title}</b>
                  {it.meta && <span className="confirm-item-meta">{it.meta}</span>}
                </span>
              </li>
            ))}
          </ol>
        )}

        {input && (
          <label className="modal-label confirm-input">
            {input.label}
            <input
              ref={inputRef}
              type="text"
              placeholder={input.placeholder || ""}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") accept();
                if (e.key === "Escape") onResolve(null);
              }}
            />
          </label>
        )}

        {detail && <p className="confirm-detail">{detail}</p>}

        <div className="modal-actions">
          <button className="btn" onClick={() => onResolve(null)}>{cancelLabel}</button>
          <button
            ref={okRef}
            className={"btn " + (tone === "danger" ? "btn-danger" : "btn-primary")}
            onClick={accept}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
