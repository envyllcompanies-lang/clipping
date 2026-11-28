-- Clipping data model (doc 25). Idempotent: safe to run repeatedly.

CREATE TABLE IF NOT EXISTS schema_version (version int PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());

-- Work queue (doc 25): FOR UPDATE SKIP LOCKED
CREATE TABLE IF NOT EXISTS job (
  id bigserial PRIMARY KEY,
  type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}',
  dedupe_key text,
  status text NOT NULL DEFAULT 'queued',     -- queued, running, done, failed, dead
  priority int NOT NULL DEFAULT 0,
  attempts int NOT NULL DEFAULT 0,
  max_attempts int NOT NULL DEFAULT 4,
  run_after timestamptz NOT NULL DEFAULT now(),
  locked_by text,
  locked_until timestamptz,
  last_error text,
  result jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS job_dedupe ON job(type, dedupe_key) WHERE dedupe_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS job_pick ON job(type, status, run_after, priority DESC);

CREATE TABLE IF NOT EXISTS worker_heartbeat (
  worker text PRIMARY KEY, host text, role text, seen_at timestamptz NOT NULL DEFAULT now(), info jsonb
);

CREATE TABLE IF NOT EXISTS game (
  slug text PRIMARY KEY, name text NOT NULL, twitch_id text, kick_id text, profile_path text
);

CREATE TABLE IF NOT EXISTS channel (
  id serial PRIMARY KEY, key text UNIQUE NOT NULL, language text NOT NULL, time_zone text NOT NULL,
  style_profile text, score_floor double precision NOT NULL DEFAULT 0.0, paused boolean NOT NULL DEFAULT false,
  config jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS account (
  id serial PRIMARY KEY, channel_id int NOT NULL REFERENCES channel(id), platform text NOT NULL,
  handle text, platform_account_id text, token_ref int, status text NOT NULL DEFAULT 'disconnected',
  review_status text NOT NULL DEFAULT 'pending', paused_until timestamptz, mode text NOT NULL DEFAULT 'fallback',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(channel_id, platform)
);

-- Encrypted credentials (doc 24)
CREATE TABLE IF NOT EXISTS credential (
  id serial PRIMARY KEY, platform text NOT NULL, account_id int REFERENCES account(id) ON DELETE CASCADE,
  kind text NOT NULL, secret_enc bytea NOT NULL, expires_at timestamptz, scopes text,
  refreshed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit_log (
  id bigserial PRIMARY KEY, at timestamptz NOT NULL DEFAULT now(), actor text, action text NOT NULL,
  subject text, details jsonb
);

-- Radar (doc 01)
CREATE TABLE IF NOT EXISTS creator (
  id serial PRIMARY KEY, platform text NOT NULL, platform_id text NOT NULL, handle text NOT NULL,
  language text, blocklisted boolean NOT NULL DEFAULT false, pinned boolean NOT NULL DEFAULT false,
  paused boolean NOT NULL DEFAULT false, first_seen timestamptz NOT NULL DEFAULT now(),
  UNIQUE(platform, platform_id)
);
CREATE TABLE IF NOT EXISTS creator_stat (
  id bigserial PRIMARY KEY, creator_id int NOT NULL REFERENCES creator(id), sampled_at timestamptz NOT NULL,
  live boolean NOT NULL, viewer_count int, game text, title text, language text, stream_started_at timestamptz,
  UNIQUE(creator_id, sampled_at)
);
CREATE TABLE IF NOT EXISTS creator_clip_stat (
  id bigserial PRIMARY KEY, creator_id int NOT NULL REFERENCES creator(id), day date NOT NULL,
  clips int NOT NULL, median_views double precision, UNIQUE(creator_id, day)
);
CREATE TABLE IF NOT EXISTS creator_offplatform (
  creator_id int NOT NULL REFERENCES creator(id), day date NOT NULL, median_upload_views double precision,
  PRIMARY KEY(creator_id, day)
);
CREATE TABLE IF NOT EXISTS creator_score (
  creator_id int NOT NULL REFERENCES creator(id), date date NOT NULL, language text,
  signals jsonb NOT NULL, percentiles jsonb NOT NULL, score double precision NOT NULL, rank int,
  selected boolean NOT NULL DEFAULT false, selection_reason text, below_cutoff_days int NOT NULL DEFAULT 0,
  flags jsonb NOT NULL DEFAULT '{}',
  PRIMARY KEY(creator_id, date)
);

-- Recorder (doc 02)
CREATE TABLE IF NOT EXISTS stream (
  id serial PRIMARY KEY, creator_id int NOT NULL REFERENCES creator(id), platform_stream_id text,
  started_at timestamptz NOT NULL, ended_at timestamptz, status text NOT NULL DEFAULT 'recording',
  language text, vod_id text, layout jsonb,
  UNIQUE(creator_id, platform_stream_id)
);
CREATE TABLE IF NOT EXISTS recorder_lock (
  creator_id int PRIMARY KEY REFERENCES creator(id), worker text NOT NULL, stream_id int,
  locked_until timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS segment (
  id bigserial PRIMARY KEY, stream_id int NOT NULL REFERENCES stream(id), path text NOT NULL UNIQUE,
  start_utc timestamptz NOT NULL, end_utc timestamptz NOT NULL, size bigint NOT NULL DEFAULT 0,
  deleted boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS segment_stream_time ON segment(stream_id, start_utc);
CREATE TABLE IF NOT EXISTS stream_gap (
  id bigserial PRIMARY KEY, stream_id int NOT NULL REFERENCES stream(id), gap_start timestamptz NOT NULL,
  gap_end timestamptz
);

-- Chat (doc 03)
CREATE TABLE IF NOT EXISTS chat_message (
  id bigserial PRIMARY KEY, stream_id int NOT NULL REFERENCES stream(id), received_at timestamptz NOT NULL,
  platform_ts timestamptz, user_id_hash text, text text, emote_ids text[], is_sub boolean, is_mod boolean
);
CREATE INDEX IF NOT EXISTS chat_message_stream ON chat_message(stream_id, received_at);
CREATE TABLE IF NOT EXISTS chat_bucket (
  stream_id int NOT NULL REFERENCES stream(id), t_start timestamptz NOT NULL, msgs int NOT NULL,
  unique_chatters int NOT NULL, emote_share real, caps_share real, laugh_share real, hype_share real,
  copypasta_score real, velocity_z real, missing boolean NOT NULL DEFAULT false,
  PRIMARY KEY(stream_id, t_start)
);

-- Ingest (doc 04)
CREATE TABLE IF NOT EXISTS platform_clip (
  id serial PRIMARY KEY, platform text NOT NULL, clip_id text NOT NULL, broadcaster_id text, creator_id int REFERENCES creator(id),
  video_id text, vod_offset double precision, duration double precision, view_count int, views_history jsonb NOT NULL DEFAULT '[]',
  created_at timestamptz, title text, language text, downloaded_path text, abs_utc_start timestamptz,
  stream_id int REFERENCES stream(id), trend_only boolean NOT NULL DEFAULT false,
  UNIQUE(platform, clip_id)
);
CREATE TABLE IF NOT EXISTS vod (
  platform text NOT NULL, video_id text NOT NULL, creator_id int REFERENCES creator(id), created_at timestamptz,
  duration_s double precision, available boolean NOT NULL DEFAULT true, PRIMARY KEY(platform, video_id)
);

-- Heatmap (doc 05)
CREATE TABLE IF NOT EXISTS moment (
  id serial PRIMARY KEY, stream_id int NOT NULL REFERENCES stream(id), start_s double precision NOT NULL,
  end_s double precision NOT NULL, peak_s double precision NOT NULL, signals jsonb NOT NULL DEFAULT '{}',
  score double precision NOT NULL, rank int, status text NOT NULL DEFAULT 'candidate', reason text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS heatmap_curve (
  stream_id int PRIMARY KEY REFERENCES stream(id), step_s real NOT NULL, values real[] NOT NULL,
  computed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS "window" (
  id serial PRIMARY KEY, moment_id int NOT NULL REFERENCES moment(id), path text, start_utc timestamptz,
  end_utc timestamptz, status text NOT NULL DEFAULT 'requested', music_risk boolean NOT NULL DEFAULT false,
  audio jsonb, created_at timestamptz NOT NULL DEFAULT now()
);

-- Transcription (doc 06)
CREATE TABLE IF NOT EXISTS transcript (
  window_id int PRIMARY KEY REFERENCES "window"(id), language text, words jsonb NOT NULL, engine text,
  visual_only boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now()
);

-- Game events (doc 08)
CREATE TABLE IF NOT EXISTS game_event (
  id bigserial PRIMARY KEY, stream_id int REFERENCES stream(id), window_id int REFERENCES "window"(id),
  t_s double precision NOT NULL, type text NOT NULL, confidence real NOT NULL, details jsonb NOT NULL DEFAULT '{}'
);

-- Clips (docs 09-12)
CREATE TABLE IF NOT EXISTS clip (
  id serial PRIMARY KEY, moment_id int NOT NULL REFERENCES moment(id), channel_id int REFERENCES channel(id),
  creator_id int REFERENCES creator(id), edit_plan jsonb, crop_plan jsonb, packaging jsonb, style_profile text,
  status text NOT NULL DEFAULT 'planned', created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(moment_id, channel_id)
);
CREATE TABLE IF NOT EXISTS clip_version (
  id serial PRIMARY KEY, clip_id int NOT NULL REFERENCES clip(id), version_type text NOT NULL,
  path text, input_hash text, phash text, audio_fp text, duration_s double precision, validation jsonb,
  pending_posts int NOT NULL DEFAULT 0, status text NOT NULL DEFAULT 'planned', targets jsonb NOT NULL DEFAULT '[]',
  thumbnail bytea, created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(clip_id, version_type)
);
CREATE TABLE IF NOT EXISTS gate_result (
  id bigserial PRIMARY KEY, clip_version_id int NOT NULL REFERENCES clip_version(id), check_name text NOT NULL,
  passed boolean NOT NULL, reason text, created_at timestamptz NOT NULL DEFAULT now()
);

-- Publishing (doc 16)
CREATE TABLE IF NOT EXISTS post (
  id serial PRIMARY KEY, clip_version_id int NOT NULL REFERENCES clip_version(id), account_id int NOT NULL REFERENCES account(id),
  platform text NOT NULL, platform_post_id text, status text NOT NULL DEFAULT 'scheduled', scheduled_at timestamptz NOT NULL,
  posted_at timestamptz, attempts int NOT NULL DEFAULT 0, next_attempt_at timestamptz, error text, fields jsonb,
  upload_session text, fallback boolean NOT NULL DEFAULT false, priority double precision NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(clip_version_id, account_id)
);
CREATE TABLE IF NOT EXISTS post_transition (
  id bigserial PRIMARY KEY, post_id int NOT NULL REFERENCES post(id), at timestamptz NOT NULL DEFAULT now(),
  from_status text, to_status text NOT NULL, error text
);
CREATE TABLE IF NOT EXISTS quota_use (
  id bigserial PRIMARY KEY, account_id int REFERENCES account(id), platform text NOT NULL, scope text NOT NULL,
  at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS fallback_task (
  id serial PRIMARY KEY, post_id int REFERENCES post(id), platform text NOT NULL, kind text NOT NULL,
  details jsonb, done boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now()
);

-- Analytics (doc 22)
CREATE TABLE IF NOT EXISTS post_stat (
  id bigserial PRIMARY KEY, post_id int NOT NULL REFERENCES post(id), sampled_at timestamptz NOT NULL,
  views bigint, likes bigint, comments bigint, shares bigint, saves bigint, retention double precision,
  followers_gained bigint, UNIQUE(post_id, sampled_at)
);
CREATE TABLE IF NOT EXISTS clip_feature (
  clip_version_id int PRIMARY KEY REFERENCES clip_version(id), features jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS weights (
  id serial PRIMARY KEY, component text NOT NULL, version int NOT NULL, "values" jsonb NOT NULL,
  fitted_at timestamptz NOT NULL DEFAULT now(), holdout_score double precision, active boolean NOT NULL DEFAULT false,
  explanation text, UNIQUE(component, version)
);
CREATE TABLE IF NOT EXISTS bandit_arm (
  id serial PRIMARY KEY, experiment text NOT NULL, arm text NOT NULL, alpha double precision NOT NULL DEFAULT 1,
  beta double precision NOT NULL DEFAULT 1, pulls int NOT NULL DEFAULT 0, UNIQUE(experiment, arm)
);
CREATE TABLE IF NOT EXISTS digest (
  id serial PRIMARY KEY, week date UNIQUE NOT NULL, body jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);

-- Storage (doc 21)
CREATE TABLE IF NOT EXISTS file (
  id bigserial PRIMARY KEY, path text UNIQUE NOT NULL, kind text NOT NULL, size bigint NOT NULL DEFAULT 0,
  owner_type text, owner_id bigint, created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz,
  deleted_at timestamptz, missing boolean NOT NULL DEFAULT false
);

-- Dashboard (doc 23)
CREATE TABLE IF NOT EXISTS command (
  id serial PRIMARY KEY, kind text NOT NULL, args jsonb NOT NULL DEFAULT '{}', status text NOT NULL DEFAULT 'pending',
  created_by text, created_at timestamptz NOT NULL DEFAULT now(), done_at timestamptz, result jsonb
);
CREATE TABLE IF NOT EXISTS alert (
  id serial PRIMARY KEY, kind text NOT NULL, severity text NOT NULL DEFAULT 'warning', message text NOT NULL,
  subject text, created_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz
);
CREATE TABLE IF NOT EXISTS system_flag (key text PRIMARY KEY, value jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS app_user (
  id serial PRIMARY KEY, email text UNIQUE NOT NULL, password_hash text NOT NULL, totp_secret_enc bytea,
  is_owner boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now()
);

-- Accounts tool (doc 27)
CREATE TABLE IF NOT EXISTS alias (
  id serial PRIMARY KEY, provider text NOT NULL, provider_id text, address text NOT NULL, code text UNIQUE NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS account_slot (
  id serial PRIMARY KEY, code text NOT NULL, platform text NOT NULL, alias_id int REFERENCES alias(id), email text,
  handle_planned text, handle_final text, handle_status text, display_name text, password_enc bytea,
  phone_used boolean NOT NULL DEFAULT false, status text NOT NULL DEFAULT 'not_started', archived boolean NOT NULL DEFAULT false,
  email_rejected boolean NOT NULL DEFAULT false, connected_account_id int REFERENCES account(id),
  updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(code, platform)
);
CREATE TABLE IF NOT EXISTS profile_kit (
  code text PRIMARY KEY, bio_per_platform jsonb NOT NULL, avatar_path text, banner_path text
);

-- Languages (doc 28)
CREATE TABLE IF NOT EXISTS language_sample (
  id bigserial PRIMARY KEY, code text NOT NULL, platform text NOT NULL, ts timestamptz NOT NULL, viewers int NOT NULL,
  channels int NOT NULL, creators_over_floor int, UNIQUE(code, platform, ts)
);
CREATE TABLE IF NOT EXISTS language_week (
  code text NOT NULL, week date NOT NULL, audience_hours double precision, depth int, clip_channels int,
  opportunity double precision, value double precision, ours double precision, score double precision, rank int,
  flags jsonb NOT NULL DEFAULT '{}', PRIMARY KEY(code, week)
);
CREATE TABLE IF NOT EXISTS language_action (
  id serial PRIMARY KEY, code text NOT NULL, action text NOT NULL, reason text, replaces text,
  created_at timestamptz NOT NULL DEFAULT now(), status text NOT NULL DEFAULT 'open'
);

-- Eval (doc 30)
CREATE TABLE IF NOT EXISTS eval_run (
  id serial PRIMARY KEY, kind text NOT NULL, stage text NOT NULL, dataset_version text, code_version text,
  config_hash text, started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz, passed boolean
);
CREATE TABLE IF NOT EXISTS eval_metric (
  run_id int NOT NULL REFERENCES eval_run(id) ON DELETE CASCADE, metric text NOT NULL, value double precision,
  baseline double precision, threshold double precision, passed boolean, PRIMARY KEY(run_id, metric)
);
CREATE TABLE IF NOT EXISTS eval_example (
  id bigserial PRIMARY KEY, run_id int NOT NULL REFERENCES eval_run(id) ON DELETE CASCADE, example_id text,
  metric text, value double precision, notes text
);

INSERT INTO schema_version(version) VALUES (1) ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS segment_feature (
  segment_id bigint PRIMARY KEY REFERENCES segment(id) ON DELETE CASCADE, audio_db real[] NOT NULL, voice real[] NOT NULL,
  scene real[] NOT NULL, music real[]
);

ALTER TABLE account ADD COLUMN IF NOT EXISTS health jsonb NOT NULL DEFAULT '{}';
ALTER TABLE clip_version ADD COLUMN IF NOT EXISTS rerenders int NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS claim (
  id serial PRIMARY KEY, post_id int REFERENCES post(id), account_id int REFERENCES account(id), kind text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz
);

CREATE TABLE IF NOT EXISTS verification_code (
  id serial PRIMARY KEY, slot_code text NOT NULL, platform text NOT NULL, code text NOT NULL, expires_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS heatmap_signal (
  stream_id int NOT NULL REFERENCES stream(id) ON DELETE CASCADE, name text NOT NULL, "values" real[] NOT NULL,
  PRIMARY KEY(stream_id, name)
);

CREATE TABLE IF NOT EXISTS creator_profile (
  creator_id int PRIMARY KEY REFERENCES creator(id), identity jsonb NOT NULL DEFAULT '{}', baselines jsonb NOT NULL DEFAULT '{}',
  reaction_style text, style_weights jsonb, signature_phrases jsonb NOT NULL DEFAULT '{}', moment_type_mix jsonb NOT NULL DEFAULT '{}',
  negative_patterns jsonb NOT NULL DEFAULT '{}', dialect text, hours_seen double precision NOT NULL DEFAULT 0, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS creator_segment (
  id bigserial PRIMARY KEY, stream_id int NOT NULL REFERENCES stream(id) ON DELETE CASCADE, start_s double precision NOT NULL,
  end_s double precision NOT NULL, label text NOT NULL, confidence real NOT NULL
);
CREATE TABLE IF NOT EXISTS creator_collab (
  creator_a int NOT NULL REFERENCES creator(id), creator_b int NOT NULL REFERENCES creator(id), stream_overlap double precision,
  sessions int NOT NULL DEFAULT 0, offset_s double precision, last_seen timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(creator_a, creator_b)
);
CREATE TABLE IF NOT EXISTS moment_analysis (
  window_id int PRIMARY KEY REFERENCES "window"(id) ON DELETE CASCADE, type text, type_confidence real, gameplay_score real,
  reaction_score real, payoff_s real, beat_s real, story_beat_id text, start_s real, end_s real, hook_style text, signals jsonb
);

ALTER TABLE segment_feature ADD COLUMN IF NOT EXISTS extra jsonb;

-- doc 07/31 "music is the subject": keep the song, route by platform; claims tracked per platform (22)
ALTER TABLE clip ADD COLUMN IF NOT EXISTS music_subject boolean NOT NULL DEFAULT false;
