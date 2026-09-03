# Sports Editorial roles and permissions

This table describes the active application permissions. Permissions are enforced by the server as well as by the controls shown in the interface.

| Capability | Researcher | Sub-editor | FIS specialist | Supervisor |
| --- | --- | --- | --- | --- |
| View all stat sheets | No | Yes | Yes | Yes |
| View assigned stat sheets | Yes | Yes | Yes | Yes |
| Create new stat sheets | No | Yes | No | Yes |
| Edit core stat-sheet data | No | No | No | Yes |
| Edit own assigned sheets | Yes | Yes | Yes | Yes |
| Edit any stat sheet | No | Yes | Yes | Yes |
| Submit for sub-edit review | Yes | Yes | Yes | Yes |
| Return a sheet to In Progress | No | Yes | Yes | Yes |
| Approve for publication | No | Yes | Yes | Yes |
| Publish to FIS / export JSON | No | Yes | Yes | Yes |
| Withdraw a published FIS sheet | No | Yes | Yes | Yes |
| Allocate researchers | No | No | No | Yes |
| Allocate sub-editors | No | No | No | Yes |
| Manage users and permissions | No | No | No | Yes |
| Force-unlock or take over a locked sheet | No | No | No | Yes |
| Import official FIS results and catalogues | No | No | No | Yes |
| Access Stat Insights | Read only | Yes | Yes | Yes |
| Primary queue/dashboard scope | Assigned work only | Full editorial queue | Full editorial and FIS queue | Full operational overview |

## Role summaries

- **Researcher:** prepares content on assigned stat sheets and submits it for sub-edit. Core data is read-only.
- **Sub-editor:** can open and edit any sheet, return work to In Progress, approve it, and perform emergency FIS publication or withdrawal. Core data and allocation remain Supervisor-only.
- **FIS specialist:** can review, edit, approve, publish, withdraw, and export sheets, but cannot create sheets or perform administrative, allocation, core-data, import, or lock-override operations.
- **Supervisor:** has complete operational access, including core data, assignment, user administration, imports, and deliberate force-unlock/takeover.

## Workflow stages

`In Progress` → `In Sub Edit` → `Approved` → `Published FIS`

- Returning a sheet from `In Sub Edit` moves it back to `In Progress`.
- Editing an Approved or Published FIS sheet returns it to `In Progress` and requires review and approval again.
- Withdrawing or publishing uses the configured FIS boundary. The application must remain in mock mode until live FIS access is explicitly authorised and configured.

## Interpretation notes

- “Edit any stat sheet” means editorial content can be changed while the user owns the valid editing lock. It does not grant permission to change core data.
- Core data includes title, client and event metadata, dates, canonical event identifiers, and researcher/sub-editor assignments.
- The optional Sub-editor permission to import official FIS results is disabled in the current implementation.
- Stat Insights is available to Researchers for reference, but official-result imports and catalogue refreshes are Supervisor-only.
