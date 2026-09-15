# Sports Editorial standalone extraction specification

Status: proposed extraction baseline  
Audience: AMP Media and implementation team  
Source system: CXMS Sports Editorial pilot  
Target: standalone, AMP-owned, multi-customer application  
Working name: `AMP_stats_sheets` until AMP confirms the final name

## 1. Purpose

This specification defines what will move from the CXMS repository into the
standalone Sports Editorial application, what must be refactored, and what is
outside the initial agreed product.

The extraction is not a rewrite of the editorial workflow. The working
submission, research, review, locking, administration, export and FIS
publishing behaviour will be carried across. Identity, tenancy, deployment and
database setup will be replaced with standalone equivalents.

The existing CXMS application remains the reference implementation until the
standalone application has passed role-by-role regression and acceptance tests.

## 2. Product boundary

### 2.1 Initial core product

The initial AMP product includes:

- Supabase Auth sign-in, sign-out, invitation and password recovery;
- AMP customer workspaces and workspace selection;
- per-workspace Researcher, Sub-editor, Supervisor and FIS Specialist roles;
- user activation/deactivation and role administration;
- stat-sheet creation and atomic AMP ID allocation;
- researcher and sub-editor allocation;
- research, submission, sub-editing and approval;
- shared FIS Specialist review queue;
- safe edit locking, takeover and release;
- event, competition, country and athlete catalogue management;
- athlete identification by FIS code/competitor ID, country and ski sponsor;
- entity annotation and the existing first-athlete-mention link rule;
- JSON preview/export and publication preview;
- controlled FIS preview, publish, update and withdrawal;
- supervisor stat-sheet administration and audit trail; and
- the operational All Stat Sheets queue.

The All Stat Sheets queue is core workflow. It is not the Beta Dashboard.

### 2.2 Paid add-ons, excluded from the initial product

The following are retained as potential separately commissioned modules but are
not included in the initial standalone delivery:

1. **Operational Dashboard (Beta)**
   - summary and attention metrics;
   - upcoming deadlines and workflow counts; and
   - the supervisor Dashboard page.
2. **Stat Insights (Beta)**
   - historical result ingestion;
   - result coverage/provenance analysis;
   - statistical and editorial discovery engines;
   - insight filters, scenarios and explainability; and
   - the Stat Insights page and import operation.

Add-ons must not be exposed merely by hiding navigation. Their routes,
services, templates and database objects should only be registered or installed
when the workspace has the corresponding entitlement.

### 2.3 Explicitly left behind

- CXMS marketing and demonstration pages;
- Data Explorer, Trade Ledger, Level Crossing and other CXMS services;
- NPS Me authentication, password hashes and shared identity tables;
- the CXMS site header, footer, favicon, branding and global navigation;
- the CXMS Heroku application, deployment metadata and repository history not
  belonging to Sports Editorial; and
- the current process-local demo-role switcher in production.

## 3. Target architecture

### 3.1 Ownership

The target GitHub repository, Heroku applications, Supabase organisation and
projects, domain and production credentials are owned by AMP. The developer is
granted named individual access appropriate to development and support.

### 3.2 Application modules

Suggested target layout:

```text
app/
  auth/                  Supabase Auth session integration
  workspaces/            customer tenancy and membership
  editorial/             stat-sheet workflow
  catalogue/             events, countries, competitions and athletes
  publishing/            JSON and FIS transformation/client
  addons/
    dashboard/           paid Operational Dashboard module
    stat_insights/       paid historical analytics module
templates/
static/
supabase/
  master.sql             fresh core installation
  migrations/            subsequent core changes
  addons/                separately installable add-on schemas
tests/
```

This layout is a destination, not a requirement for a large rewrite before the
first test. Behaviour should be moved in small, testable slices.

The repository and application package use the temporary name
`AMP_stats_sheets` until AMP confirms the permanent product name. Python must be
the latest stable version supported by the selected Heroku stack and all
required production dependencies when the standalone project is created. Its
major/minor version must then be pinned and upgraded through tested changes,
rather than changing implicitly during deployment.

## 4. Identity and workspace contract

### 4.1 Identity

Supabase Auth replaces the current NPS Me-derived `app_users` password model
and the application's self-signed JWT cookie.

The application must obtain a verified Supabase user ID for every protected
request. It must not store or verify user password hashes.

Required identity data:

```text
profiles
  user_id        uuid, primary key, references auth.users(id)
  full_name      text
  is_active      boolean
  created_at     timestamptz
  updated_at     timestamptz
```

Password creation, password reset, token expiry and identity verification are
provided by Supabase Auth. Application-level controls must still include CSRF
protection, secure cookie/session configuration, login abuse protection where
applicable, and fail-closed production configuration.

### 4.2 Workspaces

One workspace represents one AMP customer, initially FIS. Users may belong to
multiple workspaces and may have a different editorial role in each.

```text
workspaces
  id             uuid, primary key
  name           text
  slug           text, unique
  is_active      boolean
  settings       jsonb
  created_at     timestamptz
  updated_at     timestamptz

workspace_memberships
  workspace_id   uuid, references workspaces(id)
  user_id        uuid, references profiles(user_id)
  editorial_role researcher | sub_editor | supervisor | fis_specialist
  is_active      boolean
  created_at     timestamptz
  updated_at     timestamptz
  primary key (workspace_id, user_id)
```

Every operational record is scoped by `workspace_id`. The active workspace must
come from a verified membership, never directly from an untrusted request
value. Cross-workspace access must be denied both in application queries and by
database RLS policies.

The current role-checking concepts can be retained, but `current_user()` must
be replaced by a request identity containing the verified user, active
workspace and active membership role.

Users with exactly one active workspace enter it automatically after sign-in.
No workspace selector is shown in the normal single-workspace case. A selector
is required only for a user who is authorised for more than one workspace, or
for an AMP platform administrator acting across customers.

Data entry uses one shared core workflow across customers. Customer differences
belong in workspace configuration and payload adapters. A customer-specific
input variation is introduced only when onboarding identifies a genuine data
capture requirement that cannot be represented by the shared workflow.

### 4.3 AMP platform administration

AMP management requires a platform-level view across all customers, workspaces
and payload configurations. This is distinct from the customer-facing
`supervisor` role.

The platform-administrator capability must:

- be granted only through controlled AMP administration, not by a customer
  Supervisor;
- allow workspace creation, suspension and configuration;
- allow AMP management to inspect operational state across workspaces;
- allow customer payload adapters and entitlements to be administered;
- record cross-workspace interventions in an audit trail; and
- preserve an explicit active workspace context before opening or modifying a
  customer's stat sheet.

The platform view must not merge customer records into an unscoped repository
query. Cross-customer reporting uses a deliberately privileged service with
auditable filters and actions.

### 4.4 Catalogue ownership and controlled sharing

Event, competition, country and athlete catalogue records are owned by a
workspace by default. Customer annotations and publication data always remain
workspace-specific.

AMP platform administrators may deliberately make selected catalogue records
available to another workspace. This must be implemented as an explicit link
or publication mechanism, not by removing workspace scoping. The consuming
workspace can reference or copy an approved canonical record without acquiring
access to the source workspace's submissions, annotations or credentials.
Every share/unshare action is auditable.

The detailed reference-versus-copy design can be settled during schema design,
but the default is private and no catalogue record is shared automatically.

### 4.5 Add-on entitlements

The core schema may include a small entitlement table without installing the
add-on data model:

```text
workspace_features
  workspace_id   uuid, references workspaces(id)
  feature_key    text
  enabled        boolean
  configuration  jsonb
  primary key (workspace_id, feature_key)
```

Initial feature keys are `operational_dashboard` and `stat_insights`. They are
disabled by default. Entitlement checks must happen on the server.

The core repository contains extension interfaces, entitlement checks and
navigation slots, but not the proprietary implementation of an uncommissioned
add-on. Dashboard and Stat Insights source, tests and database migrations are
maintained in a separate private extension repository/package until AMP
commissions them. Once licensed, the relevant package can be installed in the
AMP deployment and switched on per workspace using the entitlement table. This
keeps activation quick without treating add-on source as part of the initial
product delivery.

## 5. Source file classification

### 5.1 Shared foundation: move and refactor

| Current source | Treatment |
| --- | --- |
| `services/sports_editorial/__init__.py` | Replace with a standalone application/module registration boundary. |
| `services/sports_editorial/auth.py` | Do not copy as-is. Replace NPS Me tables, bcrypt and custom JWT with Supabase Auth plus workspace membership lookup. Preserve role semantics. |
| `services/sports_editorial/supabase_rest.py` | Initially reusable for server-side operational calls; separate privileged administration from user-scoped access and fail fast when production configuration is incomplete. |
| `services/sports_editorial/repository.py` | Split core workflow/catalogue persistence from result-analytics persistence; replace implicit `current_user()` workspace discovery with an explicit verified workspace context. |
| `services/sports_editorial/demo_data.py` | Retain for tests and demonstrations only; never permit silent production fallback. Remove Beta result fixtures from the core portion. |
| `services/sports_editorial/views.py` | Split into auth/workspace, core editorial, catalogue, publishing, Dashboard add-on and Stat Insights add-on blueprints. Preserve behaviour route-by-route. |
| `templates/base.html` | Replace with a standalone AMP application shell. Do not carry CXMS branding, header/footer or global CSS implicitly. |
| `static/css/sports-editorial-workspace.css` | Move, then separate core rules from Dashboard/Stat Insights rules when practical. |
| `tests/test_sports_editorial.py` | Split into core, auth/workspace, catalogue, publishing and add-on suites. Preserve relevant assertions rather than copying a single monolithic test class. |

### 5.2 Core editorial workflow: move

| Current source | Responsibility |
| --- | --- |
| `services/sports_editorial/creation.py` | Controlled stat-sheet creation options, dates and calendar selection. |
| `services/sports_editorial/calendar.py` | Repository-backed calendar adapter used by creation/review. |
| `services/sports_editorial/validation.py` | Content and workflow validation. |
| `services/sports_editorial/formatting.py` | Rich-text sanitising, plain text and entity rendering. |
| `services/sports_editorial/identifiers.py` | Stable FIS external identifier construction. |
| `services/sports_editorial/edit_locks.py` | Lock timing and public lock representation. |
| `services/sports_editorial/json_export.py` | Existing pilot JSON export; rename when the final contract is confirmed. |
| `templates/sports-editorial-workspace/queue.html` | Core All Stat Sheets queue. |
| `templates/sports-editorial-workspace/queue-modern-preview.html` | Leave behind initially. AMP selected `queue.html` as the starting production queue. Retain this only as design reference unless separately commissioned. |
| `templates/sports-editorial-workspace/submit.html` | Stat-sheet creation. |
| `templates/sports-editorial-workspace/confirmation.html` | Creation confirmation. |
| `templates/sports-editorial-workspace/research.html` | Researcher editing workflow. |
| `templates/sports-editorial-workspace/detail.html` | Sub-edit/review workflow. |
| `templates/sports-editorial-workspace/manage-stat-sheets.html` | Supervisor administration. |
| `_document_identity.html`, `_edit_lock.html`, `_editable_core_data.html` | Shared core partials. |
| `sports-editorial-creation.js` | Creation interactions. |
| `sports-editorial-submit.js` | Research editing interactions. |
| `sports-editorial-review.js` | Review and entity interactions, including athlete/country/sponsor presentation. |
| `sports-editorial-review-calendar.js` | Core calendar-field interactions. |
| `sports-editorial-edit-lock.js` | Lock heartbeat and release. |
| `sports-editorial-queue.js` | Queue interactions. |
| `sports-editorial-admin.js` | Supervisor administration. |

The corresponding routes to preserve are creation, confirmation, queue,
allocation, submission detail/research, edit-lock operations, force unlock,
stat-sheet administration and user/workspace administration. Their current URL
prefix may remain temporarily but must be configured centrally rather than
embedded in JavaScript.

### 5.3 Core catalogue and athlete enrichment: move

| Current source | Responsibility and boundary |
| --- | --- |
| `services/sports_editorial/fis_calendar.py` | FIS calendar catalogue ingestion; core while required for controlled event selection. |
| `services/sports_editorial/fis_athletes.py` | Official athlete/points-list catalogue, including FIS code, country, activity and available metadata. |
| `services/sports_editorial/fis_athlete_profiles.py` | Ski-sponsor enrichment from the official athlete profile. Core because sponsor data is used during entity selection. |
| `services/sports_editorial/fis_entities.py` | Competition and country catalogue ingestion. Keep result-analysis-only helpers outside the core interface if separable. |
| `templates/sports-editorial-workspace/calendar.html` | Supervisor event catalogue. |
| `templates/sports-editorial-workspace/athletes.html` | Supervisor athlete catalogue including nation and ski sponsor. |
| `templates/sports-editorial-workspace/competitions.html` | Supervisor country and competition catalogue. |
| `static/js/sports-editorial-catalogue.js` | Catalogue refresh interactions. |
| `scripts/backfill_fis_athlete_sponsors.py` | Retain as an explicit, resumable maintenance command; do not execute as part of schema installation. |

The core athlete record should support FIS code, competitor ID, display name,
country, gender/activity status, official profile URL, ski sponsor, source and
refresh timestamps. Historical finishes and analytical measures are not part of
the core athlete record.

### 5.4 Core publishing and FIS integration: move

| Current source | Responsibility |
| --- | --- |
| `services/sports_editorial/fis_export.py` | Validate and build the FIS Media Stat Sheets payload. |
| `services/sports_editorial/fis_client.py` | Mock/live FIS publishing, safe-event allow-list and Fixie-scoped outbound proxy. |
| `templates/sports-editorial-workspace/fis-preview.html` | FIS payload preview. |
| `templates/sports-editorial-workspace/json-preview.html` | JSON preview. |
| `templates/sports-editorial-workspace/publication-preview.html` | Publication-facing preview. |
| `static/js/sports-editorial-publication-preview.js` | Publication preview behaviour. |

Live FIS writes remain disabled until FIS supplies and validates the target
host, credentials, organisation context and safe event. Fixie must proxy only
the configured FIS API calls, not Supabase or public catalogue traffic.

The tested CXMS FIS implementation is the behavioural migration baseline. Its
payload construction, validation, mock/live safeguards and existing tests move
before any redesign is considered. Migration acceptance still requires the
same behaviour to be rerun against the standalone infrastructure; migration is
not assumed correct merely because the source application passed.

### 5.5 Operational Dashboard add-on: retain but exclude

Move to a separate private, disabled add-on package:

- `services/sports_editorial/dashboard_metrics.py`;
- `templates/sports-editorial-workspace/dashboard.html`;
- the `dashboard()` route and its imports/context preparation;
- Dashboard navigation and Beta labelling; and
- Dashboard-specific tests currently embedded near the beginning of
  `tests/test_sports_editorial.py`.

The standalone core landing route should go to the All Stat Sheets queue rather
than the Dashboard.

### 5.6 Stat Insights add-on: retain but exclude

Move to a separate private, disabled add-on package:

- `services/sports_editorial/stat_insights.py`;
- all files under `services/sports_editorial/insights/`;
- `services/sports_editorial/fis_results.py`;
- `services/sports_editorial/result_coverage.py`;
- `scripts/backfill_fis_results.py`;
- `templates/sports-editorial-workspace/stat-insights.html`;
- the `stat_insights()` and `import_stat_results()` routes;
- analytical result methods and helpers currently mixed into
  `repository.py`;
- `tests/test_stat_insights_engine.py`; and
- Stat Insights/result-import tests currently embedded in
  `tests/test_sports_editorial.py`.

The add-on owns historical race result storage. It must not be required merely
to provide the core athlete catalogue.

### 5.7 Legacy/CXMS files: leave behind

- the current root `app.py`, except as a reference for Flask configuration;
- `templates/sports-editorial.html` and `static/css/sports-editorial.css` unless
  AMP explicitly commissions a public marketing page;
- unrelated templates, static files and services;
- the current root `app.json` and its CXMS metadata;
- the broad current `requirements.txt`; and
- NPS Me compatibility documentation and environment-variable aliases.

The standalone project needs a minimal entry point, focused dependency file,
AMP-specific deployment metadata and an explicit health check.

## 6. Database extraction

### 6.1 Core master schema

The standalone `supabase/master.sql` is for a fresh project and contains final
definitions rather than replaying historical alterations. It should create:

- `profiles` linked to `auth.users`;
- `workspaces`;
- `workspace_memberships`;
- optional `workspace_features` entitlements;
- submissions, content blocks, entities and entity links;
- edit-lock fields and functions;
- audit events;
- atomic AMP ID sequence/default;
- final constraints and indexes;
- final administration RPC functions;
- RLS policies and grants; and
- a schema version marker.

The master must use final role, content-type, gender, race-status and workflow
status values directly. It must include only the final seven-argument stat-sheet
administration function and must not include the old password-based user
provisioning function.

### 6.2 Current SQL classified as core source material

The following existing files inform the master schema but are not concatenated:

- `sports_editorial_pilot.sql`;
- `sports_editorial_api_readiness.sql`;
- `sports_editorial_assignments_sprint.sql`;
- `sports_editorial_audit.sql`;
- `sports_editorial_creation_sprint.sql`;
- `sports_editorial_edit_locks.sql`;
- `sports_editorial_entity_ranges.sql`;
- `sports_editorial_fis_specialist_workflow.sql`;
- `sports_editorial_gender_open.sql`;
- `sports_editorial_season_sprint.sql`;
- `sports_editorial_shared_fis_review_queue.sql`;
- `sports_editorial_stat_sheet_administration.sql`; and
- `sports_editorial_subedit_sprint.sql`.

Historical data-conversion statements in those files are not needed for an
empty database. The existing files remain unchanged in CXMS as migration
history.

### 6.3 Add-on and maintenance SQL

These are excluded from the core master:

- `sports_editorial_results.sql` -> Stat Insights add-on schema;
- `sports_editorial_result_coverage_scope.sql` -> Stat Insights upgrade/history;
- `sports_editorial_result_athletes.sql` -> optional catalogue maintenance after
  historical results exist.

### 6.4 Required security properties

- Browser clients never receive the service-role key.
- RLS is enabled with explicit policies; enabling RLS without policies is not
  the final standalone security model.
- Membership and workspace activity are checked for every workspace operation.
- User management is implemented through approved server-side Supabase Auth
  administration, not direct password-hash insertion.
- Security-definer functions have a fixed search path, explicit validation and
  least-privilege execute grants.
- Production startup fails if auth, database or secret configuration is absent.
- Schema installation and application deployment are version-compatible.

## 7. Dependencies and configuration

### 7.1 Initial Python dependencies

Retain only dependencies proven necessary by the standalone core. The current
code directly needs Flask and Gunicorn plus the selected Supabase/Auth client
approach. `bcrypt` and `PyJWT` should be removed when custom authentication is
removed, unless a different non-authenticated use is identified.

Select the most recent stable Python release supported by Heroku and the locked
dependency set at project creation, pin its major/minor version, and record the
runtime in the repository. Durability comes from a current supported baseline
plus deliberate upgrades, not an unbounded `latest` declaration.

`pandas`, `numpy`, `scikit-learn` and `stomp.py` must not be copied merely
because they exist in the CXMS requirements. Add-on dependencies, if any, are
specified and costed with the add-on.

### 7.2 Configuration groups

Core configuration:

- Flask application secret and environment;
- Supabase project URL and appropriate server credentials;
- Supabase Auth/session settings;
- deployment URL/proxy and secure-cookie settings;
- default/seed AMP workspace setup; and
- edit-lock timeout.

FIS publishing configuration:

- API mode;
- base URL and bearer credential;
- organisation UUID where required;
- safe event allow-list;
- explicit live-publishing switch; and
- Fixie URL used only by the FIS client.

Feature configuration:

- server-side workspace entitlements for Dashboard and Stat Insights; and
- no entitlement enabled merely by the presence of front-end assets.

## 8. Extraction sequence

1. Create a new local project and independent Git history.
2. Add the minimal standalone Flask application, configuration and health check.
3. Move pure core workflow modules and establish passing unit tests.
4. Add the new Supabase Auth and workspace boundary.
5. Build and validate the fresh core master schema in a disposable project.
6. Move repository persistence with explicit workspace context.
7. Move core routes, templates and assets; make the queue the landing page.
8. Move athlete/country/sponsor catalogue functions without historical results.
9. Move FIS preview/export/client functions with live publishing locked off.
10. Extract Dashboard and Stat Insights into unregistered add-on packages.
11. Deploy to AMP-owned staging with synthetic/test users and mock FIS.
12. Complete role, tenancy, security, browser and workflow acceptance tests.
13. Perform the separately approved, narrowly scoped FIS end-to-end test.
14. Create/cut over production only after AMP and FIS acceptance.

At each stage, compare behaviour with the unchanged CXMS reference application.

## 9. Acceptance criteria for the initial core product

### 9.1 Functional

- A user can authenticate and recover access through Supabase Auth.
- A user sees only active workspaces in which they have an active membership.
- The same user can hold different roles in different workspaces.
- Each role can perform only its documented operations.
- No list, detail, search, export, lock or administration operation crosses a
  workspace boundary.
- A supervisor can manage workspace access without handling user passwords.
- A stat sheet can complete the full creation-to-publication workflow.
- Concurrent editing and supervisor intervention preserve lock safety.
- Country and current ski-sponsor information are available in athlete lookup
  where supplied by the approved source.
- FIS output remains contract-valid and live writes remain deliberately gated.
- Dashboard and Stat Insights are absent when not entitled.

### 9.2 Technical and security

- The standalone application imports no CXMS or NPS Me module.
- The fresh master schema installs successfully on an empty AMP Supabase project.
- Automated core tests pass independently of add-on tests.
- Production cannot fall back silently to process-local demo storage or demo auth.
- RLS isolation tests cover two workspaces and users with single- and
  multi-workspace memberships.
- CSRF, secure session/cookie settings, redirect validation and error handling
  are verified.
- No secret appears in the repository, browser bundle, logs or test fixtures.
- Responsive browser checks pass at desktop, tablet and mobile widths.
- Python syntax/tests, JavaScript syntax and repository diff checks pass.

### 9.3 Commercial boundary

- No Beta Dashboard or Stat Insights route is registered in the initial core
  deployment.
- Add-on source and migrations remain separable and are disabled by default.
- Enabling an add-on requires an explicit workspace entitlement and a compatible
  installed migration version.
- Any work to productionise, extend or enable these Beta modules is separately
  scoped and agreed with AMP.

## 10. Recorded decisions

1. The temporary repository and package name is `AMP_stats_sheets`; AMP will
   confirm the permanent name. The project starts on the most recent stable
   supported Python version and pins it.
2. A user with one workspace enters it automatically. Multiple-workspace and
   AMP platform-administrator users receive an explicit workspace context.
3. AMP management has a separately controlled platform-administrator view
   across customer workspaces and payload configurations.
4. Catalogue data is workspace-owned by default. AMP management can explicitly
   link approved data for selection in another workspace without sharing the
   source customer's operational records.
5. `queue.html` is the initial production queue.
6. AMP branding, domain and email sender identity will be confirmed during
   deployment preparation.
7. The current tested CXMS FIS implementation is the migration baseline. Its
   behaviour and protections must be reproduced and rerun in standalone
   staging.
8. Retention and offboarding will comply with UK GDPR and AMP's documented
   controller/processor responsibilities. Before production, AMP must approve
   a concrete retention schedule, deletion/anonymisation procedure, data export
   process, legal-hold exception and audit-retention period; `UK GDPR` alone
   does not specify those durations.
9. The core repository contains add-on interfaces and entitlement controls.
   Uncommissioned Dashboard and Stat Insights implementations and migrations
   remain in a separate private extension repository/package. Commissioned
   packages can be installed and enabled per workspace without redesigning the
   core application.

## 11. Remaining deployment confirmations

The following do not block initial local extraction but must be resolved before
production:

- permanent product, repository and Python package name;
- AMP branding, domain and transactional-email sender;
- precise UK GDPR retention/offboarding schedule and accountable owner;
- named AMP platform administrators and their approval/audit process;
- final catalogue sharing implementation (reference or controlled copy);
- final Supabase region and production runtime version; and
- standalone staging confirmation of the migrated FIS contract and first
  approved live event.
