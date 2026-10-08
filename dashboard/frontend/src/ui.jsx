/* Shared building blocks for every screen. Styles live in ui.css; the design
   reference is the "Mission Control redesign" canvas (Foundations board). */
import { useEffect, useMemo, useState } from "react";
import { PLAYLIST_COLORS } from "./api.js";

const ICONS = {
  home: "M4 11l8-7 8 7v8a1 1 0 0 1-1 1h-4v-6h-6v6H5a1 1 0 0 1-1-1z",
  ideas: "M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z",
  topics: "M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01",
  play: "M7 5l12 7-12 7z",
  pause: "M8 5v14M16 5v14",
  jobs: "M3 12h4l3-8 4 16 3-8h4",
  upload: "M12 16V4M7 9l5-5 5 5M4 20h16",
  published: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zM8 12l3 3 5-6",
  playlists: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 18l9 5 9-5",
  analytics: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  music: "M9 18V5l11-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
  settings: "M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M14 4v4M8 10v4M16 16v4",
  search: "M11 19a8 8 0 1 1 0-16 8 8 0 0 1 0 16zM21 21l-4.3-4.3",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  close: "M6 6l12 12M18 6L6 18",
  right: "M9 6l6 6-6 6",
  down: "M6 9l6 6 6-6",
  left: "M15 6l-6 6 6 6",
  external: "M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5",
  folder: "M3 7a1 1 0 0 1 1-1h5l2 2h8a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z",
  grip: "M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7",
  trash: "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13",
  check: "M5 12l5 5 9-10",
  plus: "M12 5v14M5 12h14",
  edit: "M4 20h4l10-10-4-4L4 16zM13 7l4 4",
  undo: "M9 14L4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3",
  alert: "M12 9v4M12 17h.01M10.3 3.9L2.5 17.5a2 2 0 0 0 1.7 3h15.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  chart: "M4 18V9M10 18V5M16 18v-6M22 18H2",
  screen: "M4 5h16v11H4zM9 20h6M12 16v4",
  youtube: "M3 8a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v8a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3zM10 9l5 3-5 3z",
};

export function Icon({ name, size, className = "" }) {
  return (
    <svg className={"i " + className} viewBox="0 0 24 24" aria-hidden="true"
         style={size ? { width: size, height: size } : undefined}>
      <path d={ICONS[name] || ICONS.more} />
    </svg>
  );
}

/* Status wording, one vocabulary for the whole app. `tone` picks the colour. */
export const STATUS = {
  planned: ["Planned", "idle"], missing: ["Planned", "idle"],
  draft: ["In review", "info"], rendered: ["In review", "info"],
  approved: ["Approved", "info"], rejected: ["Rejected", "bad"],
  ready: ["Ready to post", "warn"], uploaded: ["Published", "go"],
  discarded: ["Discarded", "idle"],
  done: ["Completed", "go"], running: ["Running", "go"], queued: ["Queued", "idle"],
  failed: ["Failed", "bad"], error: ["Failed", "bad"], cancelled: ["Cancelled", "idle"],
  public: ["Public", "go"], private: ["Private", "warn"], unlisted: ["Unlisted", "info"],
};

export function Chip({ tone, plain, color, children, className = "", ...rest }) {
  return (
    <span className={`chip ${tone ? "s-" + tone : ""} ${plain ? "plain" : ""} ${className}`}
          style={color ? { "--c": color } : undefined} {...rest}>
      {children}
    </span>
  );
}

export function StatusChip({ state, label }) {
  const [text, tone] = STATUS[state] || [state, "idle"];
  return <Chip tone={tone}>{label || text}</Chip>;
}

export const playlistColor = (series) => PLAYLIST_COLORS[series] || "#98a4b8";

export function PlaylistChip({ series, name }) {
  return <Chip color={playlistColor(series)}>{name || series}</Chip>;
}

export function Btn({ kind = "", size, icon, iconOnly, children, className = "", type = "button", ...rest }) {
  const cls = ["btn", kind, size === "sm" ? "sm" : "", iconOnly ? "icon" : "", className].filter(Boolean).join(" ");
  return (
    <button type={type} className={cls} aria-label={iconOnly || undefined} title={iconOnly || undefined} {...rest}>
      {icon && <Icon name={icon} />}
      {!iconOnly && children}
    </button>
  );
}

export function PageHeader({ title, sub, children }) {
  return (
    <header className="top">
      <div>
        <h1>{title}</h1>
        {sub && <div className="sub">{sub}</div>}
      </div>
      <span className="spacer" />
      {children}
    </header>
  );
}

export function Search({ value, onChange, placeholder = "Search", label, small, style }) {
  return (
    <label className={"search" + (small ? " sm" : "")} style={style}>
      <Icon name="search" />
      <input type="search" value={value} placeholder={placeholder}
             aria-label={label || placeholder} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

/* options: [{ value, label, count }] */
export function Seg({ value, onChange, options, label }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" className={o.value === value ? "on" : ""}
                aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}{o.count != null && <span className="n">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Tabs({ value, onChange, options, label }) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" role="tab" aria-selected={o.value === value}
                className={o.value === value ? "on" : ""} onClick={() => onChange(o.value)}>
          {o.label}{o.count != null && <span className="num faint">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Select({ value, onChange, options, label, small }) {
  return (
    <select className={"select" + (small ? " sm" : "")} aria-label={label} value={value}
            onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={String(o.value ?? o)} value={o.value ?? o}>{o.label ?? o}</option>
      ))}
    </select>
  );
}

export function Stat({ label, value, note, tone, card = true, small }) {
  return (
    <div className={(card ? "card " : "") + "stat"}>
      <div className="lbl">{label}</div>
      <div className="val" style={{ fontSize: small ? 24 : undefined, color: tone ? `var(--${tone})` : undefined }}>
        {value}
      </div>
      {note && <div className="note">{note}</div>}
    </div>
  );
}

export function Bar({ pct = 0, color, running, height, style }) {
  const w = Math.max(0, Math.min(100, pct));
  return (
    <div className={"bar" + (running ? " run" : "")} style={{ "--c": color, height, ...style }}
         role="progressbar" aria-valuenow={Math.round(w)} aria-valuemin={0} aria-valuemax={100}>
      {w > 0 && <i style={{ width: w + "%" }} />}
    </div>
  );
}

export function Banner({ tone = "warn", title, children, actions, role = "status" }) {
  const c = { warn: "#ffc857", bad: "#ff6b6b", go: "#c8f560", info: "#7fd4ff" }[tone];
  return (
    <div className="banner" style={{ "--c": c }} role={role}>
      <div style={{ flex: "1 1 240px", minWidth: 0 }}>
        <b>{title}</b>
        {children && <div className="muted" style={{ fontSize: 13 }}>{children}</div>}
      </div>
      {actions}
    </div>
  );
}

export function Empty({ icon = "topics", title, children, action }) {
  return (
    <div className="empty">
      <div className="ico"><Icon name={icon} /></div>
      <b>{title}</b>
      {children && <span style={{ fontSize: 13 }}>{children}</span>}
      {action}
    </div>
  );
}

/* Skeleton rows in the shape of a list, shown while a screen's data loads. */
export function SkeletonRows({ rows = 6 }) {
  return (
    <div className="stack" style={{ padding: 12 }} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="rowf" style={{ flexWrap: "nowrap" }}>
          <div className="skel" style={{ width: 36, height: 36 }} />
          <div style={{ flex: 1 }}>
            <div className="skel" style={{ height: 14, width: `${70 - (i % 3) * 12}%` }} />
            <div className="skel" style={{ height: 10, width: "32%", marginTop: 6 }} />
          </div>
          <div className="skel" style={{ width: 80, height: 22, borderRadius: 999 }} />
        </div>
      ))}
    </div>
  );
}

/* Client-side paging. Lists here top out at a few hundred rows, so the server
   keeps returning the whole list and the page is sliced in the browser. */
export function usePaged(rows, initialSize = 10, resetKey = "") {
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(initialSize);
  useEffect(() => { setPage(1); }, [resetKey, size]);
  const pages = Math.max(1, Math.ceil(rows.length / size));
  const cur = Math.min(page, pages);
  const slice = useMemo(() => rows.slice((cur - 1) * size, cur * size), [rows, cur, size]);
  return { slice, page: cur, pages, size, setPage, setSize, total: rows.length,
           from: rows.length ? (cur - 1) * size + 1 : 0, to: Math.min(cur * size, rows.length) };
}

function pageList(page, pages) {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);
  const out = [1];
  const lo = Math.max(2, page - 1), hi = Math.min(pages - 1, page + 1);
  if (lo > 2) out.push("…a");
  for (let p = lo; p <= hi; p++) out.push(p);
  if (hi < pages - 1) out.push("…b");
  out.push(pages);
  return out;
}

export function Pager({ p, noun = "", sizes = [10, 25, 50], style }) {
  if (!p.total) return null;
  return (
    <div className="pager" style={style}>
      <span>{p.from}–{p.to} of {p.total}{noun ? " " + noun : ""}</span>
      {sizes && p.total > sizes[0] && (
        <select className="select sm" aria-label="Rows per page" value={p.size}
                onChange={(e) => p.setSize(Number(e.target.value))}>
          {sizes.map((s) => <option key={s} value={s}>{s} per page</option>)}
        </select>
      )}
      {p.pages > 1 && (
        <div className="pages">
          <button type="button" aria-label="Previous page" disabled={p.page === 1}
                  onClick={() => p.setPage(p.page - 1)}>‹</button>
          {pageList(p.page, p.pages).map((n) =>
            typeof n === "number" ? (
              <button key={n} type="button" className={n === p.page ? "on" : ""}
                      aria-current={n === p.page ? "page" : undefined}
                      onClick={() => p.setPage(n)}>{n}</button>
            ) : <button key={n} type="button" disabled>…</button>
          )}
          <button type="button" aria-label="Next page" disabled={p.page === p.pages}
                  onClick={() => p.setPage(p.page + 1)}>›</button>
        </div>
      )}
    </div>
  );
}

/* A 9:16 preview: the real export thumbnail when there is one, else a tinted
   placeholder in the playlist's colour. */
export function Thumb({ item, series, small }) {
  const dims = small ? { width: 27, height: 48 } : undefined;
  const c = playlistColor(series || item?.series);
  if (item?.has_thumb) {
    return <img className="thumb" src={`/api/thumb/${item.key}`} alt="" loading="lazy"
                style={{ ...dims, objectFit: "cover", "--c": c }} />;
  }
  return <div className="thumb" style={{ ...dims, "--c": c }} />;
}

/* Formatting helpers */
export const fmtNum = (n) => (n == null ? "" : Number(n).toLocaleString("en-US"));
export const fmtCompact = (n) =>
  n == null ? "" : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e4 ? `${(n / 1e3).toFixed(1)}K` : fmtNum(n);
export const fmtSecs = (s) => (s == null ? "" : `${Math.round(s)}s`);
export function fmtDuration(secs) {
  if (secs == null) return "";
  const s = Math.round(secs);
  return s >= 60 ? `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s` : `${s}s`;
}
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"];
/* "Today 23:06", "Yesterday 09:10", "3 Sept 23:18", "12 Mar 2025" */
export function fmtWhen(iso, { time = true } = {}) {
  if (!iso) return "";
  const d = new Date(String(iso).replace(" ", "T"));
  if (isNaN(d)) return String(iso);
  const now = new Date();
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86400000);
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  const date = diff === 0 ? "Today" : diff === 1 ? "Yesterday"
    : `${d.getDate()} ${MONTHS[d.getMonth()]}${d.getFullYear() !== now.getFullYear() ? " " + d.getFullYear() : ""}`;
  return time ? `${date} ${hm}` : date;
}
export const MODE_LABEL = {
  bar_race: "Bar race", bump_race: "Rank race", line_grow: "Line", line_multi: "Head to head",
  waffle_grow: "Dot grid", manim: "Narrated scene",
};
