export default function StatsRow({ counts }) {
  const tiles = [
    [counts.uploaded, "✅ UPLOADED"],
    [counts.ready, "⏳ READY"],
    [counts.rendered, "🎬 RENDERED"],
    [counts.total, "◈ TOPICS"],
  ];
  return (
    <section className="stats">
      {tiles.map(([num, label]) => (
        <div className="stat" key={label}>
          <div className="stat-num">{num}</div>
          <div className="stat-label">{label}</div>
        </div>
      ))}
    </section>
  );
}
