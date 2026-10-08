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
    confirmLabel = "Confirm",
    cancelLabel = "Cancel",
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
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <h2>{title}</h2>
        {message && <p>{message}</p>}

        {items?.length > 0 && (
          <ol>
            {items.map((it, i) => (
              <li key={i}>
                <span className="num faint">{i + 1}</span>
                <span>
                  <b>{it.title}</b>
                  {it.meta && <span className="muted" style={{ fontSize: 13 }}> · {it.meta}</span>}
                </span>
              </li>
            ))}
          </ol>
        )}

        {input && (
          <label className="field" style={{ marginBottom: 12 }}>
            {input.label}
            <input
              ref={inputRef}
              className="input"
              type="text"
              placeholder={input.placeholder || ""}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") accept();
              }}
            />
          </label>
        )}

        {detail && <p className="faint" style={{ fontSize: 13 }}>{detail}</p>}

        <div className="modal-actions">
          <button type="button" className="btn ghost" onClick={() => onResolve(null)}>{cancelLabel}</button>
          <button
            ref={okRef}
            type="button"
            className={"btn " + (tone === "danger" ? "danger" : "primary")}
            onClick={accept}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
