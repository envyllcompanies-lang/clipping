# Legacy YouTube uploader (@EnvyCarsLLC car videos)

Copied from the owner's working car-video pipeline (`~/envy-youtube-pipeline/uploader.py`, Apr–May 2026). It uploaded Shorts to @EnvyCarsLLC successfully. Keys, tokens, the SQLite database and videos were **not** copied.

## What it does

1. Scans `~/Desktop/car-vids` for videos and tracks them in SQLite (`videos` table: filepath, filename, car_model, status pending/uploaded/failed, uploaded_at).
2. Grabs a frame at 2 s with FFmpeg and asks Claude Vision for the car make/model (used as the title).
3. Center-crops to 9:16 (1080×1920), trims to 59 s, encodes H.264/AAC.
4. Uploads with the YouTube Data API v3 (`videos.insert`, resumable upload), public, category 2, fixed tags.
5. Deletes the temp render after upload. Daily cap: 50.

## What to reuse in doc 17 (YouTube connector)

- `get_authenticated_service()`: OAuth installed-app flow with `client_secret.json` + refresh of `token.json`. In the new system, tokens live in the encrypted credential store (doc 24), one per language channel, not a local file.
- `upload_video()`: resumable `videos.insert` call. Wrap it behind the publisher interface (doc 16), add retries/backoff, quota accounting, `publishAt` scheduling, privacy fallback until the API audit clears, and per-language titles/descriptions from packaging (14).
- Status tracking pattern → replaced by the Postgres `post` table (doc 25).

## What not to reuse

- The fixed crop and title logic (replaced by docs 09–14).
- `libx264` encode (use `h264_videotoolbox` on the M1, doc 12).
- SQLite and the `~/Desktop/car-vids` folder.

## Secrets (owner's machine only, never committed)

`client_secret.json` (Google OAuth client), `token.json` (refresh token for @EnvyCarsLLC), `.env` (`ANTHROPIC_API_KEY`). The clipping system uses its own Google Cloud project and one OAuth token per language channel.
