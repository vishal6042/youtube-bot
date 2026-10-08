import { Icon } from "../ui.jsx";

/* Navigation follows the pipeline: plan → produce → publish → learn. */
export const NAV = [
  { items: [{ id: null, icon: "home", label: "Overview" }] },
  { group: "Plan", items: [
    { id: "__ideas", icon: "ideas", label: "Ideas", count: "ideas" },
    { id: "__topics", icon: "topics", label: "Topics", count: "total" },
  ] },
  { group: "Produce", items: [
    { id: "__launch", icon: "play", label: "Render", count: "missing" },
    { id: "__history", icon: "jobs", label: "Jobs", count: "failures", alert: true },
  ] },
  { group: "Publish", items: [
    { id: "__upload", icon: "upload", label: "Upload", count: "ready", alert: true },
    { id: "__uploads", icon: "published", label: "Published", count: "uploaded" },
    { id: "__playlists", icon: "playlists", label: "Playlists" },
  ] },
  { group: "Learn", items: [{ id: "__analytics", icon: "analytics", label: "Analytics" }] },
  { group: "Library", items: [
    { id: "__music", icon: "music", label: "Music" },
    { id: "__settings", icon: "settings", label: "Settings" },
  ] },
];

export default function Sidebar({ view, setView, counts, online, running }) {
  return (
    <nav className="nav" aria-label="Main">
      <button type="button" className="brand" onClick={() => setView(null)}>
        <span className="brand-mark"><Icon name="chart" /></span>
        Data in Motion
      </button>
      {NAV.map((section, i) => (
        <div key={section.group || i}>
          {section.group && <div className="grp">{section.group}</div>}
          {section.items.map((n) => {
            const count = n.count ? counts[n.count] : null;
            // Alert counts only appear when there is something to act on.
            const show = n.alert ? count > 0 : count != null;
            return (
              <button
                key={n.id ?? "home"}
                type="button"
                className={"item" + (view === n.id ? " on" : "")}
                aria-current={view === n.id ? "page" : undefined}
                onClick={() => setView(n.id)}
              >
                <Icon name={n.icon} />
                {n.label}
                {n.id === "__launch" && running && <span className="dot live" style={{ marginLeft: "auto" }} />}
                {show && !(n.id === "__launch" && running) && (
                  <span className={"count" + (n.alert ? " alert" : "")}>{count}</span>
                )}
              </button>
            );
          })}
        </div>
      ))}
      <div className="nav-foot" role="status">
        <span className={"dot " + (online == null ? "idle" : online ? "live" : "off")} />
        {online == null ? "Connecting" : online ? "Dashboard connected" : "Connection lost"}
      </div>
    </nav>
  );
}
