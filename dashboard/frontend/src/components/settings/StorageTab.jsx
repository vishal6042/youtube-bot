import { useEffect, useMemo, useState } from "react";
import { api } from "../../api.js";
import {
  Banner, Btn, Chip, Empty, Pager, Search, SkeletonRows, Stat, fmtWhen, usePaged,
} from "../../ui.jsx";

/* Disk retention: edit the policy, preview exactly what a clean-up would
   delete, and run it. The preview is always a dry run; the server only deletes
   on an explicit POST to /api/retention/apply, confirmed here with the real
   folder list first. */

const FIELDS = [
  { key: "output_days_after_export", label: "Delete working files after", unit: "days from export",
    hint: "Only counted once the video has been exported. An unexported render is the only copy there is." },
  { key: "export_days_after_upload", label: "Delete finished videos after", unit: "days from upload",
    hint: "Counted from the day it went live on YouTube, never from the day it was made." },
  { key: "stale_warn_days", label: "Warn about unposted videos after", unit: "days waiting",
    hint: "Only a warning. Nothing unposted is ever deleted, however old it gets." },
];

const KIND = { output: "Working files", export: "Finished video" };
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function size(bytes) {
  if (!bytes) return "0 MB";
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(2)} GB` : `${Math.round(bytes / 1e6)} MB`;
}

export default function StorageTab({ data, reload, toast, confirm }) {
  const [policy, setPolicy] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");

  useEffect(() => {
    if (data?.policy) { setPolicy(data.policy); setDirty(false); }
  }, [data]);

  const items = useMemo(() => (data?.available ? [
    ...data.output.map((i) => ({ ...i, kind: "output" })),
    ...data.export.map((i) => ({ ...i, kind: "export" })),
  ] : []), [data]);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((i) => `${i.title} ${i.key} ${i.reason}`.toLowerCase().includes(needle));
  }, [items, q]);

  const paged = usePaged(rows, 10, q);

  if (!data) {
    return <section className="card" aria-label="Storage"><SkeletonRows rows={5} /></section>;
  }

  if (!data.available) {
    return (
      <section className="card" aria-label="Storage">
        <Empty icon="alert" title="Storage information is unavailable"
               action={<Btn size="sm" icon="refresh" onClick={reload}>Try again</Btn>}>
          The clean-up plan could not be worked out, so nothing can be deleted from here.
          <details className="more">
            <summary>Show details</summary>
            <div className="raw">{data.reason}</div>
          </details>
        </Empty>
      </section>
    );
  }

  // A topic rendered on several days has one folder per day; rows are grouped
  // per video, so the folder count is reported separately.
  const folders = items.reduce((a, i) => a + (i.copies || 1), 0);

  const recalc = async () => {
    setBusy(true);
    await reload();
    setBusy(false);
  };

  const savePolicy = async () => {
    setBusy(true);
    try {
      await api("/api/retention/policy", policy);
      toast("Storage rules saved");
      await reload();
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(false);
  };

  const runPurge = async () => {
    const ok = await confirm({
      title: `Delete ${plural(folders, "folder")}?`,
      message: `${plural(items.length, "video")} across ${plural(folders, "folder")}. Frees ${size(data.bytes)} `
             + "and cannot be undone. The videos stay on YouTube, only local files go.",
      items: items.map((i) => ({
        title: i.title + (i.copies > 1 ? ` (${i.copies} copies)` : ""),
        meta: (i.paths || []).join(", ") || i.reason,
      })),
      detail: `${plural(data.kept_unposted, "unposted video")} ${data.kept_unposted === 1 ? "is" : "are"} kept, whatever the age.`,
      confirmLabel: `Delete ${plural(folders, "folder")}`,
      tone: "danger",
    });
    if (!ok) return;
    setBusy(true);
    try {
      const r = await api("/api/retention/apply", {});
      toast(`Deleted ${plural(r.deleted, "folder")} and freed ${size(r.freed)}`);
      await reload();
    } catch (e) {
      toast(e.message, true);
    }
    setBusy(false);
  };

  return (
    <>
      <section className="card" aria-label="Storage rules">
        <div className="card-head" style={{ flexWrap: "wrap" }}>
          <h2>Storage rules</h2>
          <Chip tone={dirty ? "warn" : "go"} plain>{dirty ? "Unsaved changes" : "Saved"}</Chip>
          <span className="muted" style={{ fontSize: 13 }}>
            Days are counted from when a video was exported or uploaded, not from the folder date.
          </span>
        </div>
        <div className="cols c3">
          {FIELDS.map((f) => (
            <label className="field" key={f.key}>
              {f.label}
              <span className="num-input">
                <input
                  className="input" type="number" min="0" max="3650"
                  value={policy?.[f.key] ?? ""}
                  onChange={(e) => {
                    setPolicy((p) => ({ ...p, [f.key]: Number(e.target.value) }));
                    setDirty(true);
                  }}
                />
                <span>{f.unit}</span>
              </span>
              <span className="faint" style={{ fontSize: 12.5 }}>{f.hint}</span>
            </label>
          ))}
        </div>
        <div className="card-foot">
          <span className="note">Saving the rules deletes nothing. It only changes the plan below.</span>
          <Btn icon="refresh" disabled={busy} onClick={recalc}>Recalculate</Btn>
          <Btn kind="primary" disabled={!dirty || busy} onClick={savePolicy}>Save rules</Btn>
        </div>
      </section>

      <div className="cols c4">
        <Stat small label="Can be freed now" value={size(data.bytes)}
              note={`${plural(items.length, "video")} in ${plural(folders, "folder")}`} />
        <Stat small label="Working files" value={data.output.length}
              note={`exported ${data.policy.output_days_after_export} or more days ago`} />
        <Stat small label="Finished videos" value={data.export.length}
              note={`on YouTube for ${data.policy.export_days_after_upload} or more days`} />
        <Stat small label="Kept, not posted yet" value={data.kept_unposted} tone="go"
              note="never deleted, at any age" />
      </div>

      {data.stale?.length > 0 && (
        <Banner tone="warn"
                title={`${plural(data.stale.length, "video")} ${data.stale.length === 1 ? "has" : "have"} waited ${data.policy.stale_warn_days} or more days without being posted`}>
          {data.stale.map((s) => `${s.title} (${s.days} days)`).join(", ")}.
          These are never deleted, but a long backlog is worth a look.
        </Banner>
      )}

      <section className="card" style={{ padding: "8px 8px 16px" }} aria-label="Clean-up plan">
        <div className="rowf" style={{ padding: "12px 12px 6px" }}>
          <h2>What a clean-up would delete</h2>
          <span className="muted" style={{ fontSize: 13 }}>A preview. Nothing is deleted until you confirm.</span>
          <span className="spacer" />
          {items.length > 0 && <Search small value={q} onChange={setQ} placeholder="Search videos" />}
          {items.length > 0 && (
            <Btn kind="danger" size="sm" icon="trash" disabled={busy} onClick={runPurge}>
              Free up {size(data.bytes)}
            </Btn>
          )}
        </div>

        {items.length === 0 && (
          <Empty icon="check" title="Nothing is due for deletion">
            Everything on disk is still inside the rules above.
          </Empty>
        )}

        {items.length > 0 && rows.length === 0 && (
          <Empty icon="search" title="No videos match your search"
                 action={<Btn size="sm" onClick={() => setQ("")}>Clear search</Btn>} />
        )}

        {rows.length > 0 && (
          <>
            <div className="scroll">
              <table className="tbl">
                <thead>
                  <tr><th>Video</th><th>Copies and dates</th><th className="r">Size</th><th>Why it can go</th></tr>
                </thead>
                <tbody>
                  {paged.slice.map((i) => (
                    <tr key={i.kind + i.key}>
                      <td>
                        <div className="t">{i.title}</div>
                        <div className="k">{KIND[i.kind]}</div>
                      </td>
                      <td>
                        <div className="num">{(i.copies || 1) === 1 ? "1 copy" : `${i.copies} copies`}</div>
                        <div className="k">{(i.dates || []).join(", ")}</div>
                      </td>
                      <td className="r num">{size(i.bytes)}</td>
                      <td className="muted" style={{ fontSize: 13 }}>
                        {i.reason}
                        {i.paths?.length > 0 && (
                          <details className="more">
                            <summary>Show folders</summary>
                            <div className="raw">{i.paths.join("\n")}</div>
                          </details>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager p={paged} noun="videos" sizes={[10, 25, 50]} style={{ padding: "14px 12px 0" }} />
          </>
        )}
      </section>

      {data.orphans?.length > 0 && (
        <Banner tone="info"
                title={`${plural(data.orphans.length, "export folder")} (${size(data.orphans.reduce((a, o) => a + o.bytes, 0))}) ${data.orphans.length === 1 ? "does" : "do"} not belong to any current topic`}>
          Leftovers from an older folder layout. They are left alone because the rules cannot
          judge them. Delete them by hand if you know they are no longer needed.
          <details className="more">
            <summary>Show folders</summary>
            <div className="raw">{data.orphans.map((o) => `${o.path}  (${size(o.bytes)})`).join("\n")}</div>
          </details>
        </Banner>
      )}

      {data.runs?.length > 0 && (
        <section className="card" aria-label="Last runs">
          <div className="card-head"><h2>Last runs</h2></div>
          <ul className="kv stack" style={{ gap: 10 }}>
            {data.runs.map((r) => (
              <li key={r.id}>
                <span>{fmtWhen(r.ran_at)}</span>
                <span className="muted">
                  {r.dry_run ? "Preview only, nothing deleted"
                    : `${r.output_purged + r.export_purged} deleted`}
                  {!r.dry_run && <span className="num" style={{ marginLeft: 12, color: "var(--text)" }}>{size(r.bytes_freed)}</span>}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
