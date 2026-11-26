# SammyTV family accounts: prepared for review

Prepared 26 November 2026. This update is local only. No production database changes, accounts, invitations, emails or deployment have been made by this work.

## What the experience does

| Visitor | Experience |
| --- | --- |
| Signed out, opening `/sammytv` | Goes to a styled welcome/sign-in screen. Tabs offer **I’m watching** and **I’m a parent**. No collection data is shown. |
| Child with an approved account | Signs in with username/password and opens their family's approved collection. No child email or date of birth is collected. |
| Child needing an account | Uses a private family code to request an account. The request stays inactive until a parent recognises and approves it. |
| Parent | Uses their existing verified email/password. Opens the parent area, including the new **Family** page. |
| Additional parent in the same family | Uses a private invitation code and their own verified parent login. Can review content and manage the same children's accounts. |
| Parent starting a different family | An authorised bootstrap parent gets their own family and collection through the existing provisioning flow. No other family's content is shared. |
| Already signed in | `/sammytv` opens the collection directly. Sign-out removes both current and legacy cookie paths. |

The working assumption is **one collection per family**, shared by all its children and active parents. Three or four parents can operate separate families, or use invitations to collaborate within the same family. There is no global pool of approvals across families and no individual per-child content selection in this update.

## Parent Family page

- Pending registration requests, with explicit recognition/approval or decline.
- Add a child directly, with a display name, unique username and password. Parent-created accounts are active immediately.
- Create a seven-day family registration code. Creating a new one replaces the previous code. It permits requests, never catalogue access.
- Pause/restore child access. Pausing disables the child membership/profile and invalidates existing sessions on their next request.
- Reset a child's password without seeing the old password. Existing sessions are invalidated; a paused account stays paused.
- List active parents and create a one-use, email-bound parent invitation, valid for 48 hours. Codes are shown once for private manual sharing; no email is sent.

Each child needs a globally unique, case-insensitive username of 3–32 ASCII letters, numbers, dots, underscores or hyphens, starting with a letter/number. Display names are 1–40 characters and can be nicknames. Passwords are 10–128 characters; memorable phrases are encouraged. Password hashes, invitation/code digests and private family records are never exposed by viewer APIs.

## Parent onboarding and boundaries

Existing parent credentials and `SAMMYTV_PARENT_EMAILS` continue to work. That setting remains the bootstrap allowlist for parents creating a new family. It is not a source of roles for children.

Invited co-parents need a **verified Supabase Auth account** for the invited email. For this first version, the owner creates/verifies those accounts through the existing administrative setup. Public parent signup, email delivery, parent password recovery and automatic invitation emails are not implemented here. The invitation does not create an Auth user or bypass email verification. An existing invited parent can sign in again without the invitation or a new allowlist entry.

One verified parent identity belongs to one family in the current schema. Invitations cannot merge or move existing families. A parent who needs to join an existing family should use the invitation on their first sign-in, before bootstrap provisioning creates a separate collection. Child accounts are app-only and do not create users in the shared project's Supabase Auth tenant.

Legacy device pairing remains available at `/sammytv/pair` and `/sammytv/devices`; those viewer memberships are unchanged. The Family page manages named child logins created through this new flow, not old anonymous paired devices. An already loaded third-party video player can continue after access is paused; subsequent app/API requests reject the revoked session.

## Implementation and validation

- New SQL: `supabase/sammytv_family_accounts.sql`. Adds only SammyTV tables/functions; does not rewrite existing identities, videos, categories or approvals.
- New modules: `credentials.py` for validation, scrypt hashes and throttling; `family.py` for parent management. Existing session and repository adapters are extended.
- Children receive viewer memberships only. Session claims do not grant roles; every private request rechecks active membership, profile, family and session version. Profile ownership is checked for parents as well as children.
- Child session creation rechecks the password-hash snapshot after verification, closing reset/disable races. Management writes lock rows and compare signed review versions; concurrent parents cannot silently overwrite each other.
- New tables have forced RLS, no browser-role grants, and service-only functions. Only invitation acceptance uses a narrowly scoped SECURITY DEFINER function to read `auth.users`, as existing parent provisioning does.
- Signed CSRF forms cover public and private writes. Auth/account POST bodies are bounded to 16 KiB. Codes are entered in forms rather than URL parameters so they do not enter request URLs or referrers.
- Database-backed throttling applies across workers/dynos: 50 attempts per observed IP/action/window and 10 per login per 15 minutes; registration requests are limited to 5 per family-code digest per hour. Unknown and unapproved usernames get the same login message and a dummy scrypt check. Buckets use HMAC digests, not plaintext usernames/IPs, and expire after two days. The network-hop interpretation assumes the existing Heroku routing setup; see [Heroku routing](https://devcenter.heroku.com/articles/http-routing). With Cloudflare in front, IP buckets may group requests at the proxy, while account/code buckets still apply.
- Family account capacity is bounded to 50 stored child accounts, including pending/declined records, with at most 20 pending requests. No permanent deletion UI is introduced.

126 local SammyTV tests pass, including 29 new account tests. They exercise unauthenticated landing, both sign-in types, pending requests, signed forms, hashing, throttling, family binding, co-parent invitations, concurrent writes, pause/reset management, logout and viewer denial. Flask tests use a fake repository, so they do not establish that the SQL runs on PostgreSQL.

Browser checks used synthetic, local-only data: desktop login/parent-family screens and phone-width login/registration/family screens, including parent sign-in and logout. No horizontal overflow was found at 390 px. PostgreSQL staging checks are prepared in `supabase/tests/sammytv_family_accounts_security.sql`; they remain to be run against a staging database. PostgreSQL is unavailable locally.

Official hashing reference: [Werkzeug password helpers](https://werkzeug.palletsprojects.com/en/stable/utils/#module-werkzeug.security). Parent authentication continues through [Supabase password authentication](https://supabase.com/docs/guides/auth/passwords).

## Rollout after review

1. Confirm the previous live-camera migration is applied. Keep the existing parent credentials/configuration and preserve current family IDs.
2. Run the new migration and its transactional regression script on a staging copy of the SammyTV schema. The script creates synthetic fixtures, including two Auth rows for invitation tests, and rolls everything back. Do not run it in production.
3. Apply `supabase/sammytv_family_accounts.sql` once to the shared **NPS Me** project, then deploy the code. The previous deployment can continue operating while the additive SQL is applied. New code requires the new RPCs. No new config vars or Python dependencies are needed.
4. Test signed-out `/sammytv`, parent sign-in, creating a child and child sign-in. Test a requested account before/after approval, then pause and reset an account in another browser.
5. Test one invited parent with a separately verified Auth login and confirm both parents see the same family, while a separately provisioned family sees none of its data.

Application rollback can restore the earlier code without deleting the additive tables. Existing family IDs, approvals and original pairing flow remain in place. Rotate shared registration/invitation codes if they are disclosed; contact the owner for parent-access changes, since a parent removal UI is outside this update.
