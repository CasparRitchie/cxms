# SammyTV implementation and setup

Phases 1–3 are deployed. The owner reported applying the Phase 2 and Phase 3 SQL and confirmed successful parent sign-in after the permissions repair on 25 November 2026. Pairing is not yet verified live. Phase 4a parent video moderation is implemented locally, awaiting its SQL migration, YouTube API key and deployment.

## What Phase 2 adds

- A private, server-rendered catalogue, categories, internal search, channel pages and pagination (48 videos per page).
- Database-generated categories. “All” and “Favourites” are navigation controls, not content categories.
- Individually approved, available, embeddable, non-age-restricted recorded YouTube videos only. A channel being enabled or marked as a favourite creator does not approve its uploads.
- A click-to-load official YouTube embed, behind an off-by-default deployment setting. Approval is checked again when the player is requested.
- Separate family, membership and profile records, isolated app sessions, server-side roles and no direct browser database access.

Preview mode stays the default and loads the synthetic catalogue from `services/sammytv/demo.py`. The real catalogue NEVER falls back to these fixtures. Local browser favourites remain a prototype feature; they are scoped by profile in catalogue mode and currently filter the current catalogue page. Persistent favourites, history, subscriptions, requests and continue watching belong to Phase 4. No viewing events are written by Phase 2.

## Database setup

1. Use the shared **NPS Me** Supabase project. There is no dedicated CXMS project. Do not use AMP SmartStat.
2. Apply `supabase/sammytv_catalogue.sql` once in the SQL Editor. It is transactional and intentionally not an idempotent replacement for an existing migration. No users or videos are seeded.
3. On a staging database, run `supabase/tests/sammytv_catalogue_security.sql`. It asserts family isolation, approval rules, disabled/excluded content, literal search, RLS and denied browser access. All synthetic fixtures roll back.
4. Provision real families, parents, viewer memberships and profiles through the Phase 3 setup flow. Add the initial categories there: Trains, Planes, Lucas Ivkovic, Comedy and Live cameras. No real person has been added by this change.

The owner reports applying the catalogue, identity and identity-permissions SQL to Supabase. The new moderation migration and database regression script have not been executed against a database in this session. Python tests use a repository double, not a real database. Passing those tests does not prove that a remote migration or RLS policy is installed.

## Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `SAMMYTV_MODE` | `preview` | `catalogue` activates private database-backed pages and APIs. Unknown values fail closed. |
| `SAMMYTV_SUPABASE_URL` | Existing `SUPABASE_URL` | Optional dedicated project; otherwise reuse CXMS's Supabase infrastructure. |
| `SAMMYTV_SUPABASE_SERVICE_ROLE_KEY` | Existing `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_SECRET_KEY` | Server only. Never place this in a template, client bundle or URL. |
| `SAMMYTV_SESSION_SECRET` | None | Independent random secret of at least 32 characters. No fallback to Flask or sports workspace secrets. |
| `SAMMYTV_YOUTUBE_PLAYBACK_ENABLED` | Off | Set exactly `1` only after parent review of provider and device limitations. |
| `SAMMYTV_YOUTUBE_API_KEY` | None | Server-only YouTube Data API v3 key for importing public video metadata and checking it again on approval. Independent of the playback setting. |

Do not enable catalogue mode for Sammy until Phase 3 sign-in/provisioning exists and database checks pass. With no dedicated session the private catalogue returns 401; administration returns 403 for a viewer. Leaving preview mode on remains safe for interface review and does not expose the real catalogue.

## Session integration contract for Phase 3

`sammytv_session` is a separate cookie with a signed HS256 token containing `sub` (SammyTV member UUID), `family_id`, `profile_id`, `session_version`, `iss=cxms:sammytv`, `aud=sammytv`, `iat` and `exp`. Maximum lifetime is 24 hours. Phase 3 must set Secure, HttpOnly, SameSite=Strict and Path=/sammytv, and implement CSRF-protected login/logout and parent provisioning. Never send tokens in URLs or localStorage.

Phase 3 adds token issuance through verified parent sign-in and one-time device pairing. A future sign-in flow must verify a parent identity before looking up their membership or issuing cookies; callers must never choose an arbitrary family/member ID.

Every private request checks current database membership, family/profile status, profile ownership and session version. The database role is authoritative; a token claiming `role=parent` does not grant access. Increment `session_version` or disable a membership to revoke its sessions. A viewer can only open their own profile; a parent may operate profiles within their family.

SammyTV sessions cannot authenticate to other CXMS apps. The module imports no sports workspace authentication or repository code. A Supabase Auth account is not created for the viewer, so this does not introduce a browser JWT that could inherit other applications' existing database permissions.

## Database access model

All seven tables use the `sammytv_` prefix, tenant IDs and composite foreign keys to prohibit cross-family references. RLS is enabled and forced. All table grants are revoked from PUBLIC, anon and authenticated, and no browser policies are granted. Catalogue functions are SECURITY INVOKER and executable only by the server service role. The parent-provisioning RPC alone uses SECURITY DEFINER (owned by postgres, search_path restricted to pg_catalog) so its fixed, schema-qualified query can check auth.users. Only service_role can execute it; browser roles cannot. Parent password verification and the email allowlist remain mandatory in Flask before calling it.

The existing server service role bypasses RLS. Therefore Flask validates identity and scopes every query to the verified family. RLS protects against direct browser database access; it is not a substitute for the server checks. The adapter only permits SammyTV resource names. Public API responses project viewer-safe fields, excluding membership/approval identities, provider IDs and moderation notes. Every video response is checked again in Python before being shown. Parent moderation writes use atomic SECURITY INVOKER RPCs which recheck the active parent, family and session version and lock the records involved. Moderation and pairing require CSRF protection.

The schema currently shares a curated catalogue across profiles in a family. Per-profile exclusions can be added later; the current design does not claim separate content permissions within one family.

## API

All routes below are under `/sammytv`, require a valid private session, and return 503 while the app remains in preview mode.

| Method / route | Behaviour |
| --- | --- |
| `GET /api/catalogue` | Reviewed videos; optional `q` (120 characters), configured category name, `channel_id`, `limit` (1–48), `offset` (0–10000). Returns `has_more`. |
| `GET /api/categories` | Enabled categories in this family. |
| `GET /api/channels` | Enabled channels with at least one viewable, individually approved video. |
| `GET /api/videos/:id` | Approved catalogue UUID only, never an arbitrary YouTube ID or URL. |
| `GET /api/videos/:id/playback` | Rechecks approval; 403 while playback is disabled; otherwise a fixed-host privacy-enhanced embed URL. |

Search is literal, case-insensitive and restricted to approved titles, descriptions and channel names. SQL receives typed JSON parameters, not interpolated SQL/search syntax. There are no YouTube search requests. Queries are bounded; recommendations are just another page of the approved catalogue. Error responses do not contain upstream responses, keys or private moderation data.

All SammyTV page/API responses use `private, no-store`, `Vary: Cookie` and `noindex`. Preview/catalogue images remain local illustrations; no third-party thumbnail request or iframe is loaded at page render. Infrastructure access logs can still contain requested routes and search queries; restrict access and retention, and never log cookies or tokens. No real name, birth date, diagnosis or email is needed for a viewer profile.

## YouTube and child safety review

Verified against official documentation on 25 November 2026:

- `rel=0` restricts related videos to the same channel. It does **not** restrict them to approved videos. `modestbranding` has no effect. [YouTube player parameters](https://developers.google.com/youtube/player_parameters).
- Privacy-enhanced embeds can still show non-personalised ads. Links can take viewers to other sites/apps; most age-restricted videos cannot play on third-party sites. Child-directed services must self-designate with YouTube even in privacy-enhanced mode. [YouTube embed guidance](https://support.google.com/youtube/answer/171780?hl=en).
- Embeds need an HTTP Referer. Therefore enabled playback uses `strict-origin-when-cross-origin`, not the preview's `no-referrer`; otherwise playback may fail with error 153. No autoplay, playlists, player API scripts, downloading or rehosting is used.

The application can control its own catalogue and recommendations. It cannot guarantee that a third-party iframe is a closed, approved-only environment. This remains unresolved for unsupervised use, which is why playback is disabled by default. Recheck embedding availability/metadata at approval and periodically in a later phase. An already loaded player cannot be instantly revoked by a database change. Live streams can change after review and remain excluded from Phase 2, even if someone manually marks them approved.

Before enabling unsupervised use, test the exact iPhone/tablet/browser with a parent-controlled passcode, app-install restrictions, browser/site restrictions and OS settings that prevent opening unrestricted YouTube/other browsers. A PWA or Guided Access can help keep an app open but must not be assumed to prevent every iframe/link escape. Test end screens, ads, share/logo links, fullscreen, keyboard/context menus, new tabs, app handoffs and deleted/age-restricted videos. If these cannot meet the requirement, keep YouTube off and investigate provider-authorised embeds with stronger controls or original/licensed content. Railway webcam operators and educational providers require permission/terms checks; their content is not implicitly approved.

The UK government's published plan anticipates under-16 social-media restrictions from spring 2027; its examples include YouTube, with further restrictions affecting livestreaming. Do not assume that showing YouTube through a curated wrapper creates an exemption. Check final regulations, platform implementation and applicability to this service before launch or commercial use. [Government fact sheet, updated 18 September 2026](https://www.gov.uk/government/publications/fact-sheet-new-rules-to-protect-children-online/fact-sheet-new-rules-to-protect-children-online).

## Validation and rollout

Run:

```bash
python3 -m unittest discover -s tests -p 'test_sammytv*.py'
python3 -m unittest discover -s tests -p test_dash.py
python3 -m unittest discover -s tests -p test_trade_ledger.py
node --check static/sammytv/app.js
git diff --check
```

Automated coverage includes session tampering/expiry/audience, role spoofing, revocation, cross-family/profile attempts, missing configuration, hidden/unapproved content, escaped database content, bounded server search/pagination, approval rechecks and sanitised failures. Real database tests and device/browser playback tests remain deployment prerequisites. This change does not set live config, apply live migrations, upload real content, create accounts or deploy Phase 2.

## Phase 3 setup and current limits

1. Apply `supabase/sammytv_identity.sql` once to the same NPS Me project after Phase 2. This creates only SammyTV identity mappings, pairing codes and service-only RPCs. It does not create Auth accounts or modify existing application tables.
   If Phase 3 was already applied before the permissions fix, apply `supabase/sammytv_identity_permissions.sql` instead of rerunning the original migration. This repairs `permission denied for table users` during parent provisioning without granting direct access to auth.users or changing records. The live error was confirmed in Supabase logs on 25 November 2026; the owner subsequently reported applying the repair and successfully signing in.
2. Set `SAMMYTV_PARENT_EMAILS` to the explicit comma-separated list of allowed parent emails. Empty means nobody can sign in. Use an existing verified Supabase Auth email/password account, or create and verify a real parent account through Supabase. No public signup, password reset or email-confirmation flow is provided here.
3. Configure an independent `SAMMYTV_SESSION_SECRET` (at least 32 random characters), server Supabase credentials and `SAMMYTV_MODE=catalogue`. Serve over HTTPS. Keep playback off.
4. Open `/sammytv/signin`. Password verification occurs server-side through Supabase Auth; provider tokens never reach the browser. First successful allowlisted login atomically provisions a family, parent profile and initial categories. Concurrent logins share the same identity mapping. Existing disabled memberships are never recreated or re-enabled by login.
5. Open `/sammytv/devices` as the parent and generate a pairing code. On the viewer device open `/sammytv/pair` and enter it. Codes contain 128 bits of randomness, are stored only as SHA-256 hashes, expire after ten minutes, are consumed atomically, and are replaced by a new code from the same parent. Every redemption creates a separate viewer membership/profile with no Supabase Auth account.
6. Sessions expire after 24 hours. Re-pair after expiry. A parent account remains separate from the paired device. To revoke a viewer immediately, disable its SammyTV membership or increment its `session_version` in Supabase; a parent-facing device revocation screen is not yet included. Sign-out clears the current browser session through a CSRF-protected POST on the devices page.

All POST forms use a separate signed, expiring CSRF cookie and require matching form tokens. Cookies are Secure, HttpOnly, SameSite=Strict, scoped to `/sammytv`. Auth/pairing routes fail closed in preview mode. Login errors are generic. Supabase Auth applies its own authentication rate limits; pairing codes use high entropy rather than short guessable PINs.

Local tests use repository doubles. Concurrent pairing redemption and denied browser grants still require database integration checks. No videos are auto-approved, and the catalogue initially has no playable content. Live cameras remain excluded by the Phase 2 live-video rule despite their category name.

## Phase 4a: parent video review

Rollout, in order:

1. In the shared **NPS Me** project, apply `supabase/sammytv_moderation.sql` once. This adds four service-only functions, keeps browser grants blocked and requests a PostgREST schema refresh. It does not alter tables, create accounts or add videos. Do not rerun the earlier catalogue/identity migrations.
2. Obtain a YouTube Data API v3 key: [Google Cloud Console](https://console.cloud.google.com/) → create/select a SammyTV project → APIs & Services → Library → enable YouTube Data API v3 → Credentials → Create credentials → API key. Restrict its API access to YouTube Data API v3. This key is used by the server; a website-referrer restriction is not appropriate for this flow. No YouTube Premium subscription is required. See [YouTube authentication](https://developers.google.com/youtube/data/guides/authentication) and [getting started](https://developers.google.com/youtube/data/getting-started).
3. Put the key in the CXMS Heroku app as `SAMMYTV_YOUTUBE_API_KEY`. Keep playback disabled during this setup. No new Python/JavaScript dependencies are needed.
4. Deploy the code and open `/sammytv/admin` as the parent. Paste an individual HTTPS YouTube watch, short, embed, live or youtu.be link. Playlist/channel links, credentials, ports and other hosts are rejected. The server extracts the ID and sends only that ID to a fixed Google API endpoint. API keys are sent in headers, never to the browser or in request URLs. Redirects are not followed; responses and timeouts are bounded.
5. Imports create **pending** records. Repeated imports return the existing video without changing its approval, notes, categories or a disabled channel. Review the title, channel and description, open the canonical YouTube link in a separate tab to watch it, select at least one category and explicitly confirm suitability. These automated metadata checks do not assess content suitability.
6. Approval retrieves metadata again. Changes to the title, description, duration or visibility flags return the video to pending review. Public, processed, embeddable, non-age-restricted recordings only; any reported regional restriction, live/upcoming broadcast or archived livestream is excluded for now. Official [video metadata reference](https://developers.google.com/youtube/data/reference/rest/v3/videos) and [videos.list endpoint](https://developers.google.com/youtube/data/reference/rest/v3/videos/list). Metadata can change again after approval; scheduled rechecks remain future work.
7. **Remove video** hides it and clears approval. This is reversible through a fresh review and approval; no permanent deletion is offered. Removal needs no provider request or API key. Future catalogue/playback requests recheck visibility, but an already loaded third-party player can keep playing.

The parent queue has status filters and bounded pagination. A signed, expiring review token binds each form to its parent, family, video and database update version. SQL locks and timestamp comparisons reject stale writes; categories must be enabled and in the same family. Viewer tokens, forged role claims and revoked sessions cannot grant moderation access. Private notes and pending metadata are not exposed by viewer APIs. Parent links are shown only to parents in catalogue mode; preview keeps its nonfunctional placeholder.

Validation: 51 local SammyTV tests cover the parent workflow, CSRF, malformed/provider URLs, metadata errors and redaction, cross-family reads/categories, role spoofing, stale forms, approval rechecks and removal. The database regression script `supabase/tests/sammytv_moderation_security.sql` is for a staging database; it exercises actual service-role RPCs, import deduplication, approval/hiding/restoring, stale writes and denied browser grants, rolling all fixtures back. It has not been run here because PostgreSQL is unavailable locally. Both parent templates render through Flask tests. Local browser preview was blocked by the environment, so desktop/mobile visual checks and live database/API integration still need verification after deployment.
