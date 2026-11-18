-- Core schema. Stages communicate through these tables.

CREATE TABLE creator (
    id            INTEGER PRIMARY KEY,
    platform      TEXT NOT NULL,          -- twitch | kick | youtube
    platform_id   TEXT NOT NULL,
    handle        TEXT NOT NULL,
    language      TEXT,
    blocklisted   INTEGER NOT NULL DEFAULT 0,
    UNIQUE (platform, platform_id)
);

CREATE TABLE creator_stat (              -- radar samples
    creator_id    INTEGER NOT NULL REFERENCES creator(id),
    sampled_at    TEXT NOT NULL,
    game          TEXT NOT NULL,
    live_viewers  INTEGER,
    clip_count    INTEGER,
    clip_views    INTEGER,
    score         REAL
);

CREATE TABLE source (                    -- recordings, VODs, downloaded clips
    id            INTEGER PRIMARY KEY,
    creator_id    INTEGER REFERENCES creator(id),
    kind          TEXT NOT NULL,          -- recording | vod | clip
    url           TEXT,
    path          TEXT,
    language      TEXT,
    started_at    TEXT,
    duration_s    REAL
);

CREATE TABLE moment (                    -- heatmap windows
    id            INTEGER PRIMARY KEY,
    source_id     INTEGER NOT NULL REFERENCES source(id),
    start_s       REAL NOT NULL,
    end_s         REAL NOT NULL,
    clip_density  REAL,
    chat_velocity REAL,
    audio_energy  REAL,
    score         REAL
);

CREATE TABLE clip (
    id            INTEGER PRIMARY KEY,
    moment_id     INTEGER NOT NULL REFERENCES moment(id),
    channel       TEXT NOT NULL,          -- brand/language channel key
    path          TEXT,
    public_url    TEXT,
    title         TEXT,
    status        TEXT NOT NULL DEFAULT 'rendered', -- rendered | gated_out | queued | posted
    created_at    TEXT NOT NULL
);

CREATE TABLE post (
    id            INTEGER PRIMARY KEY,
    clip_id       INTEGER NOT NULL REFERENCES clip(id),
    platform      TEXT NOT NULL,
    account       TEXT NOT NULL,
    status        TEXT NOT NULL,          -- queued | uploading | processing | live | failed
    platform_post_id TEXT,
    scheduled_at  TEXT,
    posted_at     TEXT,
    error         TEXT,
    UNIQUE (clip_id, platform, account)   -- idempotency: never double-post
);

CREATE TABLE post_stat (
    post_id       INTEGER NOT NULL REFERENCES post(id),
    sampled_at    TEXT NOT NULL,
    views         INTEGER,
    likes         INTEGER,
    shares        INTEGER,
    avg_watch_s   REAL
);
