import { Chip, Empty, Pager, PlaylistChip, fmtNum, fmtWhen, usePaged } from "../../ui.jsx";
import SaveBar from "./SaveBar.jsx";

const DESC_LIMIT = 5000;   // YouTube's cap on a playlist description

function stateOf(p) {
  if (p.created === false) return ["warn", "Not created on YouTube"];
  if (p.edited_since_sync) return ["info", "Edited since last sync"];
  if (p.yt_synced_at) return ["go", "Matches YouTube"];
  return ["idle", "Not synced yet"];
}

function PlaylistCard({ series, p, onEdit }) {
  const [tone, label] = stateOf(p);
  const used = (p.description || "").length;
  return (
    <section className="card" aria-label={p.name || series}>
      <div className="card-head" style={{ flexWrap: "wrap" }}>
        <PlaylistChip series={series} name={p.name || series} />
        <span className="spacer" />
        <Chip tone={tone} plain>{label}</Chip>
      </div>
      <div className="stack" style={{ gap: 14 }}>
        <label className="field">
          Name
          <input className="input" type="text" value={p.name || ""}
                 onChange={(e) => onEdit(series, "name", e.target.value)} />
        </label>
        <label className="field">
          Description
          <textarea className="input" rows={6} value={p.description || ""}
                    placeholder="Shown under the playlist title on YouTube"
                    onChange={(e) => onEdit(series, "description", e.target.value)} />
          <span className="rowf" style={{ justifyContent: "space-between", fontSize: 12.5 }}>
            <span className="faint">
              {p.yt_synced_at ? `Last checked against YouTube ${fmtWhen(p.yt_synced_at)}` : "Never checked against YouTube"}
            </span>
            <span className="num muted" style={used > DESC_LIMIT ? { color: "var(--bad)" } : undefined}>
              {fmtNum(used)} / {fmtNum(DESC_LIMIT)}
            </span>
          </span>
        </label>
        <label className="rowf" style={{ fontSize: 13.5, cursor: "pointer" }}>
          <input className="check" type="checkbox" checked={p.created !== false}
                 onChange={(e) => onEdit(series, "created", e.target.checked)} />
          Exists on YouTube
        </label>
      </div>
    </section>
  );
}

export default function PlaylistsTab({ playlists, onEdit, saveBar }) {
  const entries = Object.entries(playlists);
  const paged = usePaged(entries, 10);

  if (!entries.length) {
    return (
      <section className="card" aria-label="Playlists">
        <Empty icon="playlists" title="No playlists yet">Playlists appear here once a topic uses one.</Empty>
      </section>
    );
  }

  return (
    <>
      <section className="card" aria-label="Save playlists">
        <SaveBar {...saveBar} bare
                 note="Names and descriptions save here first. Send them to YouTube from the YouTube and channel tab." />
      </section>
      <div className="cols c2">
        {paged.slice.map(([series, p]) => (
          <PlaylistCard key={series} series={series} p={p} onEdit={onEdit} />
        ))}
      </div>
      {entries.length > 10 && <Pager p={paged} noun="playlists" sizes={[10, 25]} style={{ paddingTop: 0 }} />}
    </>
  );
}
