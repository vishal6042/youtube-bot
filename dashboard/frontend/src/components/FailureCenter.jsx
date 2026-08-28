export default function FailureCenter({ failures, onRetry, onBack }) {
  return (
    <section className="panel fail-panel">
      <div className="detail-head">
        {onBack && <button className="btn back-btn" onClick={onBack}>◂ BACK</button>}
        <div>
          <div className="pl-name">FAILURE / RETRY CENTER</div>
          <div className="pl-series">topics whose last run failed — retry re-queues the full pipeline</div>
        </div>
        {failures.length > 1 && (
          <button
            className="btn btn-mini btn-primary retry-all"
            onClick={() => onRetry(failures.map((f) => f.key))}
          >
            ⟳ RETRY ALL ({failures.length})
          </button>
        )}
      </div>

      {!failures.length && (
        <div className="empty">No failures — every topic's last run succeeded. 🎉</div>
      )}

      {failures.map((f) => (
        <div className="fail-row" key={f.key}>
          <span className="fail-key">{f.key}</span>
          <span className="fail-err" title={f.error}>{f.error || "unknown error"}</span>
          <span className="fail-when">{(f.at || "").replace("T", " ")}</span>
          <button className="btn btn-mini btn-primary" onClick={() => onRetry([f.key])}>
            ⟳ RETRY
          </button>
        </div>
      ))}
    </section>
  );
}
