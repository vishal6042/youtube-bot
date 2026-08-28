const NAV = [
  { id: null, icon: "◈", label: "Mission" },
  { id: "__launch", icon: "▶", label: "Launch Control" },
  { id: "__playlists", icon: "🎞", label: "Playlists" },
  { id: "__upload", icon: "⬆", label: "Upload Control" },
  { id: "__analytics", icon: "📈", label: "Analytics" },
  { id: "__uploads", icon: "📤", label: "Upload History" },
  { id: "__topics", icon: "📋", label: "Topic Catalog" },
  { id: "__ideas", icon: "💡", label: "Build Next" },
  { id: "__music", icon: "🎵", label: "Music Library" },
  { id: "__history", icon: "🗂", label: "Job History" },
  { id: "__settings", icon: "⚙", label: "Settings" },
];

export default function Sidebar({ view, setView, failureCount, counts }) {
  return (
    <aside className="sidebar">
      <nav className="side-nav">
        {NAV.map((n) => (
          <button
            key={n.id ?? "home"}
            className={"side-item" + (view === n.id ? " active" : "")}
            onClick={() => setView(n.id)}
          >
            <span className="side-icon">{n.icon}</span>
            <span className="side-label">{n.label}</span>
            {n.id === "__history" && failureCount > 0 && (
              <span className="side-badge" title={`${failureCount} failing topic(s)`}>
                {failureCount}
              </span>
            )}
          </button>
        ))}
      </nav>
      {counts && (
        <div className="side-foot">
          <div className="side-kv"><span>Ready</span><b>{counts.ready}</b></div>
          <div className="side-kv"><span>Uploaded</span><b>{counts.uploaded}</b></div>
          <div className="side-kv"><span>Topics</span><b>{counts.total}</b></div>
        </div>
      )}
    </aside>
  );
}
