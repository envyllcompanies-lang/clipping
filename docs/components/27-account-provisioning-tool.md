# Clipper Component 27 — Account Provisioning Tool

Nov 18, 2026

The provisioning tool prepares everything for the 60 social accounts (10 languages × 6 platforms) so the owner only has to sign up, verify and press connect. It creates one email alias per language automatically, generates passwords, checks handles, builds per-language signup worksheets, pulls verification codes from the inbox, and refuses any action that could put an account under the wrong language.

## Job and boundaries

- **Does:** email aliases (addy.io API), passwords, handle availability, display names and bios, signup worksheets, verification-code routing, inbox labels, the 60-slot account register, connect-time identity checks, and re-provisioning when a language is added or swapped.
- **Doesn't:** register accounts on social platforms, solve CAPTCHAs or verify phone numbers. Google, Meta, TikTok and Snap require a person for signup, and automated signups get accounts flagged as a network. Token storage and refresh after connect belong to Component 24; OAuth flows per platform belong to the connectors (17–20).

## Inputs

| Input | Source |
| --- | --- |
| Channel list | `config/channels/<code>.yaml` (code, language name, native name, flag, time zone, brand) |
| Platforms per channel | Same file (default: all six) |
| Brand name | `config/brand.yaml` (`name`, `handle_base`, `display_base`) |
| Alias provider key | `ALIAS_PROVIDER` (`addy` default, `simplelogin` fallback), `ALIAS_API_KEY` |
| Owner inbox | `OWNER_FORWARD_EMAIL`; Gmail API OAuth (read + settings scopes) for codes and labels |
| Fallback phone | `OWNER_PHONE` secret, shown only where a platform requires a phone |
| Language swaps | Component 28 (approved swap adds a channel config) |

## Naming scheme (no mix-ups)

Every identifier carries the language code and English language name, generated from one template so they can't drift:

| Item | Pattern | Example (Spanish) |
| --- | --- | --- |
| Email alias | `<handle_base>-<code>-<language>@<alias domain>` | `brand-es-spanish@…` |
| Alias description | `GTA6 clips · <Language> (<code>) · <platform list>` | `GTA6 clips · Spanish (es) · YouTube, TikTok, Instagram, Facebook, Threads, Snapchat` |
| Handle | `<handle_base>.<code>`; `<handle_base>_<code>` where dots aren't allowed; `<handle_base><code>` where neither is | `brand.es` / `brand_es` / `brandes` |
| Display name | `<display_base> <native language name>` | `Brand Español` |
| Inbox label | `Clipping/<CODE> <Language>` | `Clipping/ES Spanish` |
| Register slot | `<code>:<platform>` | `es:tiktok` |
| Worksheet file | `worksheets/<code>-<language>.pdf` + dashboard page | `es-spanish` |

Platform handle rules (length, allowed characters) live in `config/platforms.yaml`; the generator validates each handle against them before showing it.

## Flow

1. **Plan.** Read channel configs; compute the 60 slots (`code:platform`); diff against the register. Only missing slots get work.
2. **Alias.** For each channel without an alias: `POST` to the provider's alias endpoint with the local part and description, recipient = owner inbox. Store alias ID and address in the register. Idempotent: if an alias with that local part exists, adopt it.
3. **Inbox label.** Create a Gmail filter `to:<alias>` → label `Clipping/<CODE> <Language>`, skip inbox optional (config). Uses the Gmail API settings scope.
4. **Passwords.** 24-character random password per slot (platform-specific character rules applied), encrypted with `TOKEN_ENCRYPTION_KEY`, never logged.
5. **Handles.** For each slot, check availability by requesting the platform's public profile URL (YouTube `@handle`, TikTok, Instagram, Threads, Facebook Page vanity, Snapchat). 404 = likely free; 200 = taken; anything else = unknown. If taken, try variants in order (`_` form, compact form, `<handle_base>clips.<code>`, `<handle_base>.<code>.gta6`) and record the first free one. Re-check right before signup since availability changes.
6. **Profile kit.** Generate bio (native language, written by the LLM from a template, ≤ each platform's limit), avatar and banner (brand art with the language flag corner badge, rendered locally), stored per channel.
7. **Worksheet.** One page per language: header with flag, native and English name, code; then 6 rows (one per platform) with signup link, account type to pick, email (copy button), handle, display name, password (reveal + copy), bio, avatar/banner download, "phone required?" flag, 2FA instructions, and the **Connect** button. Status per row: `not started → signed up → connected → verified`.
8. **Codes.** A watcher polls the owner inbox (Gmail API, every 30 s while any slot is `signed up`; idle otherwise). For each new message: identify the alias it was sent to (`Delivered-To` / alias provider header) → language; identify the platform from the sender domain (`google.com`, `tiktok.com`, `mail.instagram.com`, `facebookmail.com`, `snapchat.com`); extract the code with per-platform regexes. Show it in that exact slot's row for 10 minutes, then hide it. Codes are never stored after display.
9. **Connect check.** The Connect button runs the platform's OAuth (connector 17–20). After the token comes back, read the account identity (`channel title/handle`, `username`, `page name`, `display name`, email where the API exposes it) and compare with the slot: handle must match the slot's planned handle (or its recorded variant), and the language code must appear in it. Mismatch → reject, discard token, show "This is <found>, not <slot>". Match → hand the token to Component 24's credential store and mark the slot `connected`.
10. **Verify.** After connect, a test call (read-only: list own uploads/profile) confirms posting permissions; slot becomes `verified` and the scheduler (16) may use it.

## Data stored

- `account_slot` (code, platform, alias_id, email, handle_planned, handle_final, display_name, password_enc, phone_used bool, status, connected_account_id, updated_at). Unique on (code, platform).
- `alias` (provider, provider_id, address, code, created_at). Unique on code.
- `profile_kit` (code, bio_per_platform JSON, avatar_path, banner_path).
- Audit log: every alias creation, password reveal, connect attempt (match/mismatch) with timestamp.

## Edge cases

- **Platform rejects the alias domain at signup:** the owner marks the row "email rejected"; the tool switches that slot to the fallback flow (owner-created Gmail for that slot, recorded with the same naming rules: `<handle_base>.<code>.<platform>@gmail.com` suggested).
- **Alias provider down or free-tier limit hit:** stop creating new aliases, keep existing ones, alert; config can switch to SimpleLogin for new aliases only.
- **Same platform needs two accounts for one language later:** blocked by the unique slot; adding one requires a new channel config (e.g. `es-mx`), which gets its own alias.
- **Code email arrives without a recognizable sender:** shown under "Unmatched" on the language page (matched by alias only), never in another language's rows.
- **Handle taken between check and signup:** owner presses "re-check"; next variant is offered.
- **Language swapped out (28):** slots are archived, not deleted; aliases stay active so recovery emails still arrive.

## Security

- Passwords and recovery codes encrypted at rest; reveal requires dashboard login with 2FA and is audit-logged.
- Gmail API scopes limited to reading message metadata/bodies from alias senders and managing filters.
- The register is never exported in plain text; worksheets mask passwords unless revealed in the dashboard.

## Done when

- [ ] From a fresh config, one command creates all 10 aliases, inbox labels, passwords, handle checks, profile kits and worksheets with no owner input beyond the API key.
- [ ] A test code email to each alias appears in the correct language + platform row and nowhere else.
- [ ] Connecting a deliberately wrong account to a slot is rejected with a clear message.
- [ ] Re-running the command changes nothing (idempotent).

## Open questions

- [ ] Brand name and `handle_base`.
- [ ] addy.io plan needed for 10+ aliases with API access (check current free-tier limits at setup).
