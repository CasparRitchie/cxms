# Sports Editorial pilot: temporary Supabase setup

The pilot can safely share the current NPS Me Supabase project while it is being developed. Its data lives only in tables prefixed `sports_editorial_`; existing NPS tables are not changed by the setup script.

## 1. Create the isolated tables

Open Supabase SQL Editor and run [`supabase/sports_editorial_pilot.sql`](../supabase/sports_editorial_pilot.sql).

If you ran an earlier version of the file, run it again. The statements are repeatable and the latest version adds the server-only user-provisioning function.

The script enables row-level security and deliberately creates no anonymous browser policies. Flask performs all database work server-side with the service-role key and scopes reads/writes to the signed-in workspace.

## 2. Grant an existing NPS Me user access

Find the user's `app_users.id` and their `workspace_members.workspace_id`, then run:

```sql
insert into public.sports_editorial_memberships
  (workspace_id, user_id, editorial_role)
values
  ('WORKSPACE_UUID', 'APP_USER_UUID', 'sub_editor');
```

Use `journalist` for a journalist account. A user needs an active `app_users` row, an existing `workspace_members` row, and an active sports membership.

Workspace owners and admins can subsequently open **Users** in Sports Editorial to create pilot accounts. Existing NPS Me email addresses keep their current password; new addresses receive the temporary password entered by the administrator.

## 3. Configure CXMS/Heroku

```text
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
SPORTS_EDITORIAL_REPOSITORY=supabase
SPORTS_EDITORIAL_AUTH_MODE=workspace
SPORTS_EDITORIAL_JWT_SECRET=a-long-random-secret-unique-to-cxms
```

`SUPABASE_SECRET_KEY` is also accepted temporarily for compatibility with the NPS Me variable name. Do not expose either service key to browser JavaScript.

Keep the FIS integration in simulation:

```text
FIS_API_MODE=mock
FIS_LIVE_PUBLISH_ENABLED=false
```

Live writes additionally require `FIS_API_BASE_URL`, `FIS_API_TOKEN`, at least one explicitly agreed `FIS_SAFE_EVENT_IDS` value, and the deliberate `FIS_LIVE_PUBLISH_ENABLED=true` switch.

## Moving to a customer-owned Supabase project

Run the same sports SQL in the new project, migrate only the `sports_editorial_*` rows, provide the customer project's environment variables, and recreate/map workspace users and memberships. Application views and FIS transformation code do not need to change.

The current login deliberately mirrors NPS Me's server-side password and signed HttpOnly-cookie model. Before production, move identity to Supabase Auth (or the customer's identity provider), add user-scoped RLS policies, CSRF protection, rate limiting, and account-management flows.
