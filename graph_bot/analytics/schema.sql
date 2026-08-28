-- Analytics warehouse for the "Data in Motion" channel.
--
-- Design notes that matter later:
--   * video_daily_stats is the only table that grows without bound — every
--     published video adds a row every day, forever — so it is partitioned by
--     month from the very first row. Retrofitting partitioning onto a 50M-row
--     table is a painful migration; doing it at zero rows is free.
--   * raw_analytics_row keeps every source line as jsonb. When a metric turns
--     out to be interesting later, it is re-derived from raw rather than
--     re-pulled from YouTube, which only serves rolling windows.
--   * Every import is idempotent: re-importing an overlapping date range must
--     update rows, never duplicate them.

CREATE TABLE IF NOT EXISTS analytics_import (
    id           bigserial PRIMARY KEY,
    source       text        NOT NULL UNIQUE,   -- zip filename, the natural key
    range_start  date,
    range_end    date,
    imported_at  timestamptz NOT NULL DEFAULT now(),
    rows_daily   integer     NOT NULL DEFAULT 0,
    rows_period  integer     NOT NULL DEFAULT 0,
    rows_channel integer     NOT NULL DEFAULT 0
);

-- One row per video that has ever appeared in an export.
CREATE TABLE IF NOT EXISTS video (
    video_id     text PRIMARY KEY,              -- YouTube's own id
    topic_key    text,                          -- joins back to config/topics.yaml
    series       text,
    playlist     text,
    title        text,
    published_at date,
    duration_sec integer,
    first_seen   timestamptz NOT NULL DEFAULT now(),
    last_seen    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS video_topic_key_idx ON video (topic_key);
CREATE INDEX IF NOT EXISTS video_series_idx    ON video (series);

-- The unbounded time series: one row per video per day.
CREATE TABLE IF NOT EXISTS video_daily_stats (
    video_id  text    NOT NULL REFERENCES video (video_id) ON DELETE CASCADE,
    day       date    NOT NULL,
    views     integer NOT NULL DEFAULT 0,
    import_id bigint  REFERENCES analytics_import (id) ON DELETE SET NULL,
    PRIMARY KEY (video_id, day)
) PARTITION BY RANGE (day);

CREATE INDEX IF NOT EXISTS video_daily_stats_day_idx ON video_daily_stats (day);

-- Range aggregates from "Table data.csv". These are per-report-window, not
-- daily, so the window is part of the key rather than pretending it is a day.
CREATE TABLE IF NOT EXISTS video_period_stats (
    video_id     text NOT NULL REFERENCES video (video_id) ON DELETE CASCADE,
    range_start  date NOT NULL,
    range_end    date NOT NULL,
    views        integer,
    watch_hours  numeric(12, 4),
    subscribers  integer,
    impressions  integer,
    ctr_pct      numeric(6, 3),
    -- Not every export carries every metric: YouTube's column set varies with
    -- the report you download, so these are all nullable and filled per import.
    avg_view_sec integer,
    avg_pct_viewed numeric(6, 3),
    import_id    bigint REFERENCES analytics_import (id) ON DELETE SET NULL,
    PRIMARY KEY (video_id, range_start, range_end)
);

-- Channel-wide totals for a report window, taken from the "Total" row of
-- Table data.csv. These are NOT the sum of the per-video rows: YouTube does not
-- attribute every view or subscriber to a specific video, so summing per-video
-- rows understates the channel (49 videos summed to 14 subscribers against a
-- reported 72). Always report the channel from here.
CREATE TABLE IF NOT EXISTS channel_period_stats (
    range_start    date NOT NULL,
    range_end      date NOT NULL,
    views          integer,
    watch_hours    numeric(12, 4),
    subscribers    integer,
    impressions    integer,
    ctr_pct        numeric(6, 3),
    avg_view_sec   integer,
    avg_pct_viewed numeric(6, 3),
    import_id      bigint REFERENCES analytics_import (id) ON DELETE SET NULL,
    PRIMARY KEY (range_start, range_end)
);

-- Channel-wide daily totals from "Totals.csv".
CREATE TABLE IF NOT EXISTS channel_daily_stats (
    day       date PRIMARY KEY,
    views     integer NOT NULL DEFAULT 0,
    import_id bigint  REFERENCES analytics_import (id) ON DELETE SET NULL
);

-- Landing zone: every source line exactly as it arrived.
CREATE TABLE IF NOT EXISTS raw_analytics_row (
    id          bigserial PRIMARY KEY,
    import_id   bigint NOT NULL REFERENCES analytics_import (id) ON DELETE CASCADE,
    source_file text   NOT NULL,
    row_no      integer NOT NULL,
    payload     jsonb  NOT NULL
);
CREATE INDEX IF NOT EXISTS raw_analytics_row_import_idx ON raw_analytics_row (import_id);

-- Create the monthly partition covering p_day, if it is not there already.
-- Called by the importer for every distinct month in a file, so a partition can
-- never be missing at insert time. There is deliberately no DEFAULT partition:
-- silently misfiled rows are worse than a loud error.
CREATE OR REPLACE FUNCTION ensure_daily_partition(p_day date) RETURNS text AS $$
DECLARE
    p_start date := date_trunc('month', p_day)::date;
    p_end   date := (date_trunc('month', p_day) + interval '1 month')::date;
    p_name  text := format('video_daily_stats_%s', to_char(p_start, 'YYYY_MM'));
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = p_name) THEN
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF video_daily_stats FOR VALUES FROM (%L) TO (%L)',
            p_name, p_start, p_end
        );
    END IF;
    RETURN p_name;
END;
$$ LANGUAGE plpgsql;

-- Convenience view: daily views with the topic/series attached, which is how
-- almost every question about performance actually gets asked.
CREATE OR REPLACE VIEW video_daily AS
SELECT d.day,
       d.video_id,
       v.topic_key,
       v.series,
       v.playlist,
       v.title,
       v.published_at,
       v.duration_sec,
       d.day - v.published_at AS days_live,
       d.views
FROM video_daily_stats d
JOIN video v USING (video_id);
