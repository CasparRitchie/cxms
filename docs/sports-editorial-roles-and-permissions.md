# Sports Editorial roles and permissions

This table describes the active application permissions. Permissions are enforced by the server as well as by the controls shown in the interface.

| Capability | Researcher | Sub-editor | FIS specialist | Supervisor |
| --- | --- | --- | --- | --- |
| View all stat sheets | No | Yes | Yes | Yes |
| View assigned stat sheets | Yes | Yes | Yes | Yes |
| Create new stat sheets | No | Yes | No | Yes |
| Edit core stat-sheet data | No | No | No | Yes |
| Edit own assigned sheets | Yes | Yes | During assigned FIS review | Yes |
| Edit any stat sheet | No | Yes, before FIS review | No | Yes |
| Submit for sub-edit review | Yes | Yes | Yes | Yes |
| Return a sheet to In Progress | No | Yes | Yes | Yes |
| Approve for FIS review | No | Yes | No | Yes |
| Final publish to FIS | No | No | Assigned sheets | Yes |
| Withdraw from FIS review or Published FIS | No | Yes | No | Yes |
| Allocate researchers | No | No | No | Yes |
| Allocate sub-editors | No | No | No | Yes |
| Manage users and permissions | No | No | No | Yes |
| Inactivate/reactivate stat sheets | No | No | No | Yes |
| Mark a race cancelled/reinstated | No | No | No | Yes |
| Assign FIS specialists | No | No | No | Yes |
| Force-unlock or take over a locked sheet | No | No | No | Yes |
| Import official FIS results and catalogues | No | No | No | Yes |
| Access Stat Insights | Read only | Yes | Yes | Yes |
| Primary queue/dashboard scope | Assigned work only | Full editorial queue | Full editorial and FIS queue | Full operational overview |

## Role summaries

- **Researcher:** prepares content on assigned stat sheets and submits it for sub-edit. Core data is read-only.
- **Sub-editor:** can open and edit any sheet, return work to In Progress, approve it, and perform emergency FIS publication or withdrawal. Core data and allocation remain Supervisor-only.
- **FIS specialist:** can edit an explicitly assigned sheet during Awaiting FIS Review and perform its final FIS publication. The role cannot approve, withdraw, administer, allocate, import or override locks.
- **Supervisor:** has complete operational access, including core data, assignment, user administration, imports, and deliberate force-unlock/takeover.

## Workflow stages

`In Progress` → `In Sub Edit` → `Approved` → `Awaiting FIS Review` → `Published FIS`

- Returning a sheet from `In Sub Edit` moves it back to `In Progress`.
- AMP can withdraw an Awaiting FIS Review or Published FIS sheet to `In Sub Edit`; the assigned specialist loses editing access and any specialist lock is invalidated.
- Editing an Approved sheet can still return it to `In Progress` for a wider correction and fresh research cycle.
- Withdrawing or publishing uses the configured FIS boundary. The application must remain in mock mode until live FIS access is explicitly authorised and configured.

## Interpretation notes

- “Edit any stat sheet” means editorial content can be changed while the user owns the valid editing lock. It does not grant permission to change core data.
- Core data includes title, client and event metadata, dates, canonical event identifiers, and researcher/sub-editor assignments.
- The optional Sub-editor permission to import official FIS results is disabled in the current implementation.
- Stat Insights is available to Researchers for reference, but official-result imports and catalogue refreshes are Supervisor-only.
