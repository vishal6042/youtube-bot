import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon } from "../../ui.jsx";
import "../../screens/publish.css";

/* The "more" popover used on queue cards and published rows.
   items: [{ label, icon, onClick, tone: "bad", disabled }], falsy entries are skipped. */
export default function MoreMenu({ label = "More actions", items }) {
  const [pos, setPos] = useState(null);
  const btn = useRef(null);
  const menu = useRef(null);
  const list = items.filter(Boolean);

  const toggle = () => {
    if (pos) { setPos(null); return; }
    const r = btn.current.getBoundingClientRect();
    const right = Math.max(8, window.innerWidth - r.right);
    const need = list.length * 40 + 16;
    // Opens downward unless that would run off the bottom of the window.
    setPos(r.bottom + need > window.innerHeight && r.top > need
      ? { right, bottom: window.innerHeight - r.top + 6 }
      : { right, top: r.bottom + 6 });
  };

  useEffect(() => {
    if (!pos) return undefined;
    const buttons = () => [...(menu.current?.querySelectorAll("button:not(:disabled)") || [])];
    buttons()[0]?.focus({ preventScroll: true });

    const onDown = (e) => {
      if (!menu.current?.contains(e.target) && !btn.current?.contains(e.target)) setPos(null);
    };
    const onKey = (e) => {
      if (e.key === "Escape") {
        setPos(null);
        btn.current?.focus();
      } else if (e.key === "Tab") {
        setPos(null);
      } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const b = buttons();
        if (!b.length) return;
        const i = b.indexOf(document.activeElement);
        const step = e.key === "ArrowDown" ? 1 : -1;
        b[(i + step + b.length) % b.length].focus();
      }
    };
    // The menu is fixed to where the button was, so any scroll or resize closes it.
    const onMove = () => setPos(null);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
    };
  }, [pos]);

  return (
    <>
      <button ref={btn} type="button" className="btn icon sm ghost" aria-label={label} title="More actions"
              aria-haspopup="menu" aria-expanded={!!pos} onClick={toggle}>
        <Icon name="more" />
      </button>
      {pos && createPortal(
        <div ref={menu} className="pop-menu" role="menu" aria-label={label} style={pos}>
          {list.map((it) => (
            <button key={it.label} type="button" role="menuitem" disabled={it.disabled}
                    className={it.tone === "bad" ? "bad" : ""}
                    onClick={() => { setPos(null); it.onClick(); }}>
              {it.icon ? <Icon name={it.icon} /> : <span className="gap" />}
              {it.label}
            </button>
          ))}
        </div>,
        document.body
      )}
    </>
  );
}
