-- Operational state: what has happened, not what exists.
--
-- The filesystem stays the source of truth for what has been rendered and
-- exported — output/ and export/ are scanned, never mirrored here — because a
-- second copy of "what exists" is a second thing that can drift. These tables
-- hold the records that only exist because someone did something: an upload was
-- posted, a video was discarded, a queue was reordered, a job ran.
--
-- The reason this moved off JSON is concurrency, not size. Both the CLI and the
-- dashboard write these, so a whole-file rewrite could lose an update or leave a
-- truncated file behind. Every write here is a single atomic statement.

CREATE TABLE IF NOT EXISTS upload_log (
    topic_key   text PRIMARY KEY,
    uploaded_at timestamptz NOT NULL,
    url         text,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS discarded (
    topic_key    text PRIMARY KEY,
    discarded_at timestamptz NOT NULL,
    reason       text NOT NULL DEFAULT '',
    from_path    text,   -- where the export folder was
    moved_to     text    -- where it sits under export/_discarded/
);

-- A manual upload order. Absent rows simply mean "no custom order".
CREATE TABLE IF NOT EXISTS queue_order (
    topic_key text PRIMARY KEY,
    position  integer NOT NULL,
    saved_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS queue_order_position_idx ON queue_order (position);

-- Render jobs. The columns are what the UI filters and sorts on; the full job
-- record (agents, steps, per-topic results, log tail) stays in payload, which is
-- the shape the dashboard already speaks.
CREATE TABLE IF NOT EXISTS job (
    id          text PRIMARY KEY,
    label       text,
    status      text NOT NULL,
    keys        text[] NOT NULL DEFAULT '{}',
    current_key text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    started_at  timestamptz,
    finished_at timestamptz,
    payload     jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS job_created_idx ON job (created_at DESC);
CREATE INDEX IF NOT EXISTS job_status_idx  ON job (status);

-- Render/export history, so deleting files does not erase the fact that a topic
-- was ever made. The filesystem still answers "is there a file I can play or
-- upload right now?"; this answers "has this topic been rendered before?" —
-- which must survive retention deleting the folder.
CREATE TABLE IF NOT EXISTS topic_lifecycle (
    topic_key        text PRIMARY KEY,
    first_rendered_at date,
    last_rendered_at  date,
    last_exported_at  date,
    export_path      text,   -- last known export folder (may since be purged)
    output_purged_at timestamptz,
    export_purged_at timestamptz,
    updated_at       timestamptz NOT NULL DEFAULT now()
);

-- One row per retention pass, so purges are auditable after the fact.
CREATE TABLE IF NOT EXISTS retention_run (
    id             bigserial PRIMARY KEY,
    ran_at         timestamptz NOT NULL DEFAULT now(),
    dry_run        boolean NOT NULL,
    output_purged  integer NOT NULL DEFAULT 0,
    export_purged  integer NOT NULL DEFAULT 0,
    bytes_freed    bigint  NOT NULL DEFAULT 0,
    detail         jsonb   NOT NULL DEFAULT '[]'::jsonb
);

-- Videos staged for upload. Clicking the arrow in the queue stages a video here;
-- nothing reaches YouTube until the batch is run from Upload Control.
CREATE TABLE IF NOT EXISTS upload_batch (
    topic_key text PRIMARY KEY,
    position  integer NOT NULL,
    added_at  timestamptz NOT NULL DEFAULT now(),
    state     text NOT NULL DEFAULT 'queued',   -- queued|running|done|failed
    stage     text,
    pct       integer NOT NULL DEFAULT 0,
    url       text,
    error     text,
    warnings  jsonb NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX IF NOT EXISTS upload_batch_position_idx ON upload_batch (position);

-- Daily YouTube Data API spend. The day is the US/Pacific date because that is
-- when Google resets the quota, not local midnight. One full upload costs 1702
-- units against 10,000/day, so the real ceiling is 5 videos — the batch cap is
-- derived from what is left, never a hardcoded number.
CREATE TABLE IF NOT EXISTS api_quota (
    day        date PRIMARY KEY,
    units      integer NOT NULL DEFAULT 0,
    uploads    integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Channel & playlist copy (moved off data/brand.json 2026-09-04). One row of
-- channel identity, one row per playlist. yt_* columns remember what YouTube
-- last reported so the dashboard can show a local-vs-live diff and push edits.
CREATE TABLE IF NOT EXISTS brand_channel (
    id           smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    tagline      text NOT NULL DEFAULT '',
    description  text NOT NULL DEFAULT '',
    updated_at   timestamptz NOT NULL DEFAULT now(),
    yt_synced_at timestamptz
);

CREATE TABLE IF NOT EXISTS brand_playlist (
    series         text PRIMARY KEY,
    name           text NOT NULL,
    description    text NOT NULL DEFAULT '',
    created        boolean NOT NULL DEFAULT false,
    yt_playlist_id text,
    updated_at     timestamptz NOT NULL DEFAULT now(),
    yt_synced_at   timestamptz
);

-- Live counts pulled from the YouTube Data API (videos.list / channels.list —
-- ~1 unit per 50 videos, so a full sync costs almost nothing). Snapshots, not
-- upserts: history is cheap and shows growth between analytics exports.
CREATE TABLE IF NOT EXISTS channel_stats_live (
    fetched_at  timestamptz PRIMARY KEY DEFAULT now(),
    subscribers bigint,
    views       bigint,
    video_count integer
);

CREATE TABLE IF NOT EXISTS video_stats_live (
    video_id       text NOT NULL,
    fetched_at     timestamptz NOT NULL DEFAULT now(),
    views          bigint,
    likes          bigint,
    comments       integer,
    privacy_status text,
    PRIMARY KEY (video_id, fetched_at)
);
CREATE INDEX IF NOT EXISTS video_stats_live_latest_idx
    ON video_stats_live (video_id, fetched_at DESC);
