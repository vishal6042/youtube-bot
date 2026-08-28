import { AGENTS, AGENT_TEXT } from "../api.js";

const SHORT = {
  video: "VIDEO", music: "MUSIC", mixing: "MIX",
  subtitle: "TITLES", exporting: "EXPORT", thumbnail: "THUMB",
};

function orchestratorState(job, queue, history) {
  if (job) {
    const agents = job.agents || {};
    const actives = AGENTS.filter((a) => agents[a.key] === "active");
    let s = job.stage || "starting";
    if (!AGENT_TEXT[s]) s = "starting";
    const failed = Object.values(job.results || {}).some((r) => r.status === "failed");
    if (failed && !job.stage) s = "error";
    // With parallel branches running, the headline names every live agent.
    const headline = actives.length > 1
      ? actives.map((a) => SHORT[a.key]).join(" ∥ ")
      : AGENT_TEXT[s] || s.toUpperCase();
    const key = job.current_key || job.label;
    return [s, headline, key + (job.label !== key ? " · " + job.label : "")];
  }
  if (queue.length) return ["queued", AGENT_TEXT.queued, `${queue.length} job(s) queued`];
  const last = history[0];
  if (last && last.status === "failed")
    return ["error", AGENT_TEXT.error, `last job failed · ${last.label}`];
  return ["idle", AGENT_TEXT.idle, "no active job — sub-agents on standby"];
}

export default function AgentNetwork({ job, queue, history, onCancel }) {
  const [state, headline, detail] = orchestratorState(job, queue, history);
  const agents = job ? job.agents || {} : {};
  const allDone = job && job.stage === "exported";

  const nodeState = (a) => {
    if (!job) return "idle";
    if (allDone) return "done";
    return agents[a.key] || "idle";
  };

  return (
    <section className="panel agent-panel network-panel" data-state={state}>
      <div className="panel-title">AGENT ORCHESTRATOR · PIPELINE NETWORK</div>

      <div className="net-tree">
        <div className="net-orch">
          <svg className="agent" viewBox="0 0 220 220" role="img" aria-label="Orchestrator status">
            <defs>
              <radialGradient id="coreGlow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="var(--agent)" stopOpacity="0.9" />
                <stop offset="55%" stopColor="var(--agent)" stopOpacity="0.25" />
                <stop offset="100%" stopColor="var(--agent)" stopOpacity="0" />
              </radialGradient>
            </defs>
            <circle className="ring ring-outer" cx="110" cy="110" r="96" />
            <circle className="ring ring-dash" cx="110" cy="110" r="82" />
            <g className="orbit orbit-a"><circle className="sat" cx="110" cy="24" r="4" /></g>
            <g className="orbit orbit-b"><circle className="sat" cx="110" cy="40" r="3" /></g>
            <circle className="ring ring-inner" cx="110" cy="110" r="58" />
            <circle className="core-glow" cx="110" cy="110" r="54" fill="url(#coreGlow)" />
            <circle className="core" cx="110" cy="110" r="34" />
            <g className="eye">
              <rect className="eye-scan" x="80" y="106" width="60" height="8" rx="4" />
            </g>
          </svg>
          <div className="agent-status">
            <div className="agent-state">{headline}</div>
            <div className="agent-detail">{detail}</div>
          </div>
        </div>

        <div className="net-stem" aria-hidden="true" />

        <div className="net-row">
          {AGENTS.map((a) => {
            const st = nodeState(a);
            return (
              <div key={a.key} className={"anode " + st}>
                <div className="anode-orb"><span className="anode-icon">{a.icon}</span></div>
                <div className="anode-label">{a.label}</div>
                <div className="anode-status">
                  {st === "active" ? "◉ ACTIVE" : st === "done" ? "✓ DONE"
                    : st === "failed" ? "✕ FAILED" : "· IDLE"}
                </div>
              </div>
            );
          })}
        </div>

        {job && (
          <div className="job-actions">
            <button className="btn btn-danger" onClick={onCancel}>✕ ABORT JOB</button>
          </div>
        )}
      </div>
    </section>
  );
}
