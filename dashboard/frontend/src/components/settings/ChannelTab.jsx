import {
  Banner, Bar, Btn, Chip, Icon, PlaylistChip, Stat, fmtCompact, fmtNum, fmtWhen,
} from "../../ui.jsx";
import SaveBar from "./SaveBar.jsx";

const ABOUT_LIMIT = 1000;   // YouTube's cap on the About description
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const lowerDay = (when) => when.replace(/^(Today|Yesterday)/, (d) => d.toLowerCase());

function textState({ dirty, sync, channelDiffers, channel }) {
  if (dirty) return ["warn", "Unsaved changes"];
  if (sync) return channelDiffers ? ["warn", "Edited here, not on YouTube yet"] : ["go", "Matches YouTube"];
  if (channel.edited_since_sync) return ["info", "Edited since last sync"];
  if (channel.yt_synced_at) return ["go", "Matches YouTube"];
  return ["idle", "Not synced yet"];
}

function Connection({ stats, sync, auth, ytBusy, dirty, channelDiffers, pushables, onPull, onPush }) {
  const ch = sync?.channel || stats?.channel;
  const synced = sync?.fetched_at || stats?.channel?.fetched_at;
  const changes = (channelDiffers ? 1 : 0) + pushables.length;
  const expired = auth?.needs_reauth;
  const name = sync?.channel?.title;

  return (
    <section className="card" aria-label="YouTube connection">
      <div className="card-head" style={{ flexWrap: "wrap" }}>
        <span className={"dot " + (expired ? "off" : ch ? "live" : "idle")} />
        <h2>
          {expired ? "YouTube sign-in needs renewing"
            : ch ? `Connected to YouTube${name ? " as " + name : ""}`
            : "No YouTube data yet"}
        </h2>
        <span className="spacer" />
        <span className="muted" style={{ fontSize: 13 }}>
          {synced ? `last synced ${lowerDay(fmtWhen(synced))}` : "never synced"}
        </span>
        <Btn size="sm" icon="refresh" disabled={ytBusy} onClick={onPull}>
          {ytBusy ? "Syncing" : "Sync now"}
        </Btn>
      </div>

      <div className="cols c4">
        <Stat card={false} small label="Subscribers" value={ch ? fmtCompact(ch.subscribers) : "–"} />
        <Stat card={false} small label="Total views" value={ch ? fmtCompact(ch.views) : "–"} />
        <Stat card={false} small label="Videos" value={ch ? fmtNum(ch.video_count) : "–"} />
        <Stat
          card={false} small label="Sign-in"
          value={!auth ? "Not checked" : expired ? "Expired" : "Valid"}
          tone={!auth ? "faint" : expired ? "bad" : "go"}
          note={expired && auth.hint ? (
            <details className="more">
              <summary>How to renew</summary>
              <span className="raw" style={{ display: "block" }}>{auth.hint}</span>
            </details>
          ) : "needs renewing about weekly"}
        />
      </div>

      {sync && (
        <div className="card-foot">
          <span className="note">
            {changes > 0
              ? `${plural(changes, "edit")} made here ${changes === 1 ? "is" : "are"} not on YouTube yet.`
              : "Your saved text matches YouTube."}
            {changes > 0 && dirty && " Save your changes before sending."}
          </span>
          {changes > 0 ? (
            <Btn kind="primary" icon="upload" disabled={ytBusy || dirty} onClick={onPush}>
              Send {plural(changes, "change")} to YouTube
            </Btn>
          ) : <Chip tone="go" plain>Matches YouTube</Chip>}
        </div>
      )}
    </section>
  );
}

function Comparison({ sync, channelDiffers }) {
  return (
    <div className="cols c2">
      <section className="card" aria-label="Compared with YouTube">
        <div className="card-head"><h2>Compared with YouTube</h2></div>
        <div>
          <div className="diff-row">
            <span style={{ fontWeight: 550 }}>Channel description</span>
            <span className="spacer" />
            {channelDiffers
              ? <Chip tone="warn">Edited here, ready to send</Chip>
              : <Chip tone="go">In sync</Chip>}
          </div>
          {sync.playlists.map((p) => (
            <div className="diff-row" key={p.series}>
              <PlaylistChip series={p.series} name={p.name || p.series} />
              {p.found && p.differs && p.remote_title !== p.name && (
                <span className="faint" style={{ fontSize: 12.5 }}>called "{p.remote_title}" on YouTube</span>
              )}
              <span className="spacer" />
              {p.found && !p.differs && (
                <span className="muted num" style={{ fontSize: 12.5 }}>
                  {p.item_count == null ? "video count unknown" : plural(p.item_count, "video")}
                </span>
              )}
              {!p.found ? <Chip tone="idle">Not found on YouTube</Chip>
                : p.differs ? <Chip tone="warn">Edited here, ready to send</Chip>
                : <Chip tone="go">In sync</Chip>}
            </div>
          ))}
        </div>
      </section>

      {sync.videos?.length > 0 && (
        <section className="card" aria-label="Top videos right now">
          <div className="card-head"><h2>Top videos right now</h2></div>
          <div>
            {sync.videos.slice(0, 5).map((v) => (
              <div className="diff-row" key={v.video_id}>
                <span style={{ flex: "1 1 200px", minWidth: 0 }}>{v.title || v.topic_key}</span>
                <span className="muted num" style={{ fontSize: 12.5 }}>
                  {fmtCompact(v.views)} views · {fmtCompact(v.likes)} likes
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Rail({ data, playlists, retention, onTab }) {
  const entries = Object.entries(playlists);
  const missing = entries.filter(([, p]) => p.created === false);
  const waiting = entries.filter(([, p]) => p.edited_since_sync).length;
  const avatar = (data.images || []).find((i) => i.role === "Profile picture");
  const policy = retention?.policy;
  const head = (title, tab) => (
    <div className="card-head">
      <h2>{title}</h2><span className="spacer" />
      <Btn size="sm" kind="ghost" onClick={() => onTab(tab)}>Open tab</Btn>
    </div>
  );

  return (
    <aside className="rail">
      <section className="card" aria-label="Playlists">
        {head("Playlists", "playlists")}
        <ul className="kv stack" style={{ gap: 10 }}>
          <li><span>On YouTube</span><span className="num">{entries.length - missing.length} of {entries.length}</span></li>
          {missing.map(([series, p]) => (
            <li key={series}><span>{p.name || series}</span><Chip tone="warn" plain>Not created</Chip></li>
          ))}
          <li><span>Descriptions edited here</span><span className="num">{waiting} waiting</span></li>
        </ul>
      </section>

      <section className="card" aria-label="Brand images">
        {head("Brand images", "brand")}
        {avatar ? (
          <div className="rowf" style={{ flexWrap: "nowrap" }}>
            <img className="avatar" src={`/api/brand/${avatar.name}`} alt="" loading="lazy" />
            <div>
              <b>{avatar.role}</b>
              <div className="muted num" style={{ fontSize: 12.5 }}>
                {[avatar.dimensions, `${avatar.size_kb} KB`].filter(Boolean).join(" · ")}
              </div>
            </div>
          </div>
        ) : <span className="muted">{plural((data.images || []).length, "image")}</span>}
        <p className="faint" style={{ fontSize: 12.5, marginTop: 10 }}>
          Replacing an image keeps a backup of the old one.
        </p>
      </section>

      <section className="card" aria-label="Storage">
        {head("Storage", "storage")}
        {policy ? (
          <ul className="kv stack" style={{ gap: 10 }}>
            <li><span>Working files kept</span><span className="num">{plural(policy.output_days_after_export, "day")} after export</span></li>
            <li><span>Finished videos kept</span><span className="num">{plural(policy.export_days_after_upload, "day")} after upload</span></li>
            <li><span>Unposted videos</span><span className="num">never deleted</span></li>
          </ul>
        ) : (
          <span className="muted" style={{ fontSize: 13.5 }}>
            {retention ? "Storage information is unavailable right now." : "Checking disk use"}
          </span>
        )}
      </section>
    </aside>
  );
}

export default function ChannelTab({
  data, channel, playlists, onEdit, saveBar, stats, sync, syncError, auth, ytBusy,
  channelDiffers, pushables, onPull, onPush, retention, onTab,
}) {
  const priv = sync?.private || [];
  const about = channel.description || "";
  const used = about.length;
  const pct = (used / ABOUT_LIMIT) * 100;
  const [tone, label] = textState({ dirty: saveBar.dirty, sync, channelDiffers, channel });

  return (
    <>
      <Connection stats={stats} sync={sync} auth={auth} ytBusy={ytBusy} dirty={saveBar.dirty}
                  channelDiffers={channelDiffers} pushables={pushables} onPull={onPull} onPush={onPush} />

      {syncError && (
        <Banner tone="bad" role="alert" title="Could not sync with YouTube"
                actions={<Btn size="sm" disabled={ytBusy} onClick={onPull}>Try again</Btn>}>
          Nothing was changed. If the sign-in has expired, renew it and sync again.
          <details className="more">
            <summary>Show details</summary>
            <div className="raw">{syncError}</div>
          </details>
        </Banner>
      )}

      {priv.length > 0 && (
        <Banner
          tone="warn"
          title={`${plural(priv.length, "uploaded video")} ${priv.length === 1 ? "is" : "are"} still private on YouTube`}
        >
          Nobody can see {priv.length === 1 ? "it" : "them"} yet. Open each one in YouTube Studio and switch it to Public.
          <ul className="stack" style={{ margin: "8px 0 0", padding: 0, listStyle: "none", gap: 6 }}>
            {priv.map((v) => (
              <li key={v.video_id}>
                <a className="link rowf" style={{ display: "inline-flex", gap: 6 }} target="_blank" rel="noreferrer"
                   href={`https://studio.youtube.com/video/${v.video_id}/edit`}>
                  {v.title || v.topic_key || "Untitled video"}<Icon name="external" size={14} />
                  <span className="sr">(opens YouTube Studio in a new tab)</span>
                </a>
              </li>
            ))}
          </ul>
        </Banner>
      )}

      {sync && <Comparison sync={sync} channelDiffers={channelDiffers} />}

      <div className="split">
        <section className="card wide" aria-label="Channel text">
          <div className="card-head"><h2>Channel text</h2><Chip tone={tone} plain>{label}</Chip></div>
          <div className="stack" style={{ gap: 16 }}>
            <label className="field">
              Tagline
              <input className="input" type="text" value={channel.tagline || ""}
                     onChange={(e) => onEdit("tagline", e.target.value)} />
              <span className="faint" style={{ fontSize: 12.5 }}>Used in handle bios and on other platforms.</span>
            </label>
            <label className="field">
              About description
              <textarea className="input" rows={12} value={about}
                        aria-invalid={used > ABOUT_LIMIT || undefined}
                        onChange={(e) => onEdit("description", e.target.value)} />
              <span className="rowf" style={{ justifyContent: "space-between", fontSize: 12.5 }}>
                <span className="faint">
                  {used > ABOUT_LIMIT
                    ? `${fmtNum(used - ABOUT_LIMIT)} over YouTube's limit. YouTube will reject it.`
                    : "Shown on your channel's About page."}
                </span>
                <span className="num muted" style={used > ABOUT_LIMIT ? { color: "var(--bad)" } : undefined}>
                  {fmtNum(used)} / {fmtNum(ABOUT_LIMIT)}
                </span>
              </span>
            </label>
            <Bar pct={pct} height={4}
                 color={pct > 100 ? "var(--bad)" : pct > 90 ? "var(--warn)" : undefined} />
          </div>
          <SaveBar {...saveBar} note="Changes save here first. Nothing goes to YouTube until you send it." />
        </section>

        <Rail data={data} playlists={playlists} retention={retention} onTab={onTab} />
      </div>
    </>
  );
}
