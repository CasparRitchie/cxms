# SammyTV: player containment and provider transition

Prepared 27 November 2026. This is an implementation plan; independent playback providers and new database fields are not implemented by the thumbnail change.

The [personal-media exploration](sammytv-personal-media.md) adds a separate device-only gallery proposal, a concrete Commons crossing-video candidate and a parent-only alternative-search approach. Personal recordings need not be uploaded or hosted by SammyTV.

## What we can deliver now

Use YouTube's standard thumbnail on approved catalogue cards and the watch page. Existing items work immediately after deployment. This is normally the creator's chosen thumbnail, which may differ from the opening frame. Do not download videos to extract random frames. Thumbnail requests use a fixed image host, no referrer and anonymous CORS; broken images use local artwork. Preview/sign-in pages stay local.

YouTube controls its embedded player, including outbound logo/title/share links and related videos. It offers no documented complete link-disable option. Its policy guide explicitly disallows blocking standard links or related videos; hiding controls, putting click-blocking overlays over the iframe or relying on a restrictive sandbox would not meet the requirement. Keep normal accessibility, captions, seeking and volume controls. `rel=0` is already set and limits related videos to the same channel, which can include unapproved videos. SammyTV's own suggestions remain family-approved only. The embedded player cannot provide the same boundary.

Parent-controlled device restrictions can be tested as an additional layer on Sammy's actual device, including new tabs, app handoffs, fullscreen, end screens and keyboard/context-menu actions. Do not promise that a PWA or Guided Access closes every exit. A player with no platform links requires an authorised source with suitable player controls, ideally media we have permission to play through our own HTML5 player.

## Confirmed policy and unresolved questions

The government's fact sheet, updated 18 September 2026, names YouTube among the platforms in its proposed model, with regulations intended before the end of 2026 and implementation expected in spring 2027. Ofcom's age-assurance page, updated 16 November, still describes the forthcoming regulations and subsequent guidance consultation. This is a published direction and timetable, not evidence that every technical detail is settled.

Before changing access rules, check the actual regulations, commencement dates, Ofcom guidance and YouTube's implementation for logged-out embeds, age checks and child-directed services. Assess SammyTV's own position, including its family-only design and any future public registrations. A curated interface or parental permission must not be treated as an automatic exemption. Educational-service exemptions cannot be assumed to cover a mixed entertainment catalogue. Google also requires child-directed embedding services to self-designate, including privacy-enhanced embeds; track completion separately with the owner.

The June government announcement describes the livestreaming restriction as children broadcasting themselves. Do not infer from that announcement alone that watching a permitted railway camera is prohibited. Its hosting provider may still become unavailable to an under-16 viewer; review the final rules and each provider's terms.

## Delivery sequence

| Stage | Concrete result | Completion check |
| --- | --- | --- |
| 1. Current release | Actual thumbnails; clear player limitation; keep existing family approvals. | Existing videos display images; fallback and local-only switch work; no iframe until requested. |
| 2. One independent railway pilot | Obtain operator permission for one camera, starting with Wootton/Havenstreet candidates in the camera-source notes. Confirm availability, cost, permitted domains and any ads/links. No outreach has been sent. | Operator-supplied authorised source works on Sammy's actual device with acceptable controls. |
| 3. Provider support | Add a specific adapter for that source and a migration that supports its identifiers, permissions and status. Preserve existing YouTube records. | Per-family approval, removal, offline behaviour and fixed-host validation pass before release. |
| 4. Broaden the catalogue | Ask selected creators for original files and explicit hosting permission; source licensed train/plane footage. Budget storage, delivery and rights. | A useful selection of Sammy's favourite categories remains playable without YouTube. |
| 5. Apply final rules | Review the published requirements and provider changes; disable affected playback before any applicable deadline. | No fallback to an external platform, adult account or replacement unapproved feed. Explain unavailable items calmly within SammyTV. |

For stage 3, keep the catalogue and family/category/approval experience. Extend playback behind a server-selected provider adapter. Add operator identity, exact source identifier, permission evidence, approved domains, status and review date; never accept arbitrary iframe HTML or a caller-supplied streaming URL. SQL catalogue functions currently enforce YouTube-specific rules, so this needs a migration and database verification, not just a frontend player swap. Use separate adapters for authorised third-party embeds and licensed direct media. Limit CSP to each approved host, and keep source credentials and permission notes server-side. A changed source or provider requires fresh parent approval; do not silently transfer an approval to a different video. A live source remains a live source even if its host changes.

For licensed direct media, use native controls without platform links and signed/short-lived media URLs where supported. Handle HLS compatibility on the target devices and clear unavailable states. Do not scrape YouTube streaming URLs or rehost YouTube downloads. Independent hosting changes the player and platform dependency; it does not establish a legal exemption by itself.

## Operational controls

Today `SAMMYTV_YOUTUBE_PLAYBACK_ENABLED=0` stops new YouTube player requests. `SAMMYTV_YOUTUBE_THUMBNAILS_ENABLED=0` stops YouTube thumbnail requests on newly loaded pages. An already open iframe can continue; these are not instant revocation controls. For a complete YouTube cutover, also stop parent imports/refreshes and camera metadata requests, remove YouTube images from new pages and provide a clear unavailable state. Add a single provider-level disable switch in the provider-support stage. No configuration changes are made by this plan.

Retain family accounts, categories and review history through the transition. Avoid collecting children's ID documents or birth dates speculatively. If age assurance becomes applicable to SammyTV itself, define that requirement from final guidance and use a suitable specialist service rather than storing identity evidence ourselves. Reassess before opening registration beyond known families.

## Sources checked

- [YouTube developer policy guide](https://developers.google.com/youtube/terms/developer-policies-guide), particularly standard links, thumbnails, related videos and restrictions.
- [YouTube player parameters](https://developers.google.com/youtube/player_parameters), including `rel` and deprecated branding options.
- [YouTube embed guidance](https://support.google.com/youtube/answer/171780?hl=en), including child-directed designation and privacy-enhanced mode.
- [UK government fact sheet](https://www.gov.uk/government/publications/fact-sheet-new-rules-to-protect-children-online/fact-sheet-new-rules-to-protect-children-online).
- [Ofcom age-assurance duties](https://www.ofcom.org.uk/online-safety/protecting-children/age-assurance).
- [Government announcement, including livestreaming clarification](https://www.gov.uk/government/news/social-media-to-be-banned-for-under-16s-in-landmark-government-move-to-givekids-their-childhood-back).
- [Existing camera candidates and permission findings](sammytv-camera-sources.md). Candidate availability must be checked again before integration.
