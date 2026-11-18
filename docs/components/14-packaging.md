# Clipper Component 14 — Packaging (Titles, Captions, Hashtags)

Nov 18, 2026

Packaging writes everything around the video for each platform and language: on-screen hook text, title, post caption, hashtags, creator credit and cover choice. Text is written natively in the page's language (never translated) and tuned per platform's limits and habits.

## Job and boundaries

- **Does:** generate hook text (for Component 11; in hook-only mode this headline is the only on-screen text for the whole clip, so it must describe or tease the moment on its own), titles, descriptions/captions, hashtags and credit lines; enforce character limits; vary wording so posts aren't templated.
- **Doesn't:** post (16–20) or choose the clip (09).

## Inputs

Transcript excerpt with the payoff marked, game events, creator name and platform, the channel's language and voice notes, hook patterns from the style profile (13), and recent titles from this channel (to avoid repeats).

## Output per clip per platform

| Field | YouTube Shorts | TikTok | Instagram Reels | Facebook Reels | Threads | Snapchat |
| --- | --- | --- | --- | --- | --- | --- |
| Title | Yes (title field; keep ~60 chars to read on mobile) | No | No | No | No | No |
| Caption/description | Description + hashtags | Caption with hashtags | Caption (2,200 char API limit) | Description | Text (500 chars) | Optional text |
| Hashtags | 3–5 incl. #Shorts optional | 3–5 | 3–5 | 1–3 | 1 topic tag max via API | None |
| Credit line | "Clip from @creator (Twitch)" + link | Name in caption | Name in caption | Name in caption | Name | On-screen only |
| Cover | Payoff frame (where custom thumbnails apply) | Cover frame timestamp | Cover frame or image | — | — | — |

Threads allows one topic tag per post through the API ([Meta docs](https://developers.facebook.com/docs/threads/posts/)); Instagram captions max 2,200 characters ([Blotato](https://www.blotato.com/api/instagram)). Verify remaining limits at build time.

## Writing rules

1. **Hook text** (on screen, first 1.5–3 s): one of the profile's winning patterns: reaction ("HE DID NOT SEE THAT COMING"), question ("How did he survive this?"), number/stakes ("5 stars and one tire"), or creator-first ("xQc vs the entire police force"). Max ~40 characters per line, two lines.
2. **Titles:** front-load the payoff, name the creator when they're big (searchable), no clickbait that misrepresents the clip.
3. **Hashtags:** a fixed core set per channel (e.g. #GTA6 #GTAVI #gaming) plus 1–2 dynamic ones (creator name, event type), never more than the platform norm. Rotate so identical tag blocks don't repeat on every post.
4. **Variation:** never reuse a title or caption verbatim within the channel's last 200 posts; similarity check by embedding distance.
5. **Language:** written natively in the page language by the LLM with a style sheet of local slang and conventions; numbers and creator names untouched.
6. **Safety:** no slurs, no doxxing, no claims about real people beyond what the clip shows.

## Generation method

- One LLM call per clip returns all fields for all platforms as JSON, with lengths validated in code; overlong fields are regenerated once, then truncated at a word boundary.
- A small library of proven hook templates (from the style study and our own analytics) is offered to the LLM as examples; it fills specifics from the transcript.
- Analytics (22) tags every post with its hook pattern and title style so the system learns which patterns win per platform and language.

## Done when

- [ ] Every clip has valid fields for every target platform within limits.
- [ ] No duplicate captions across a channel's recent posts.
- [ ] Hook and title patterns are tracked as features in analytics.

## Open questions

- [ ] Brand voice per channel (hype, deadpan, informative), decided per language page.
