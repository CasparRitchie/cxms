# Camera sources checked 25 November 2026

## Crossing-camera batch, 26 November

The owner reports applying the camera migration and the collection loading again. A read-only check through the deployed CXMS adapter also successfully loaded approved catalogue rows. Four crossing-focused YouTube feeds were selected from the [East Lancashire Railway's camera page](https://www.eastlancsrailway.org.uk/railcam/) and the [WSR webcam selector](https://www.wsr.org.uk/cams.htm), whose players identify Railcam's railway channels:

| Camera | Exact stream | Watch for |
| --- | --- | --- |
| Ramsbottom Cam 3 North | [jLyy1TdfnYQ](https://www.youtube.com/watch?v=jLyy1TdfnYQ) | Station and crossing view, the example originally supplied by the owner. |
| Townsend Fold | [rKCC6_8SWmI](https://www.youtube.com/watch?v=rKCC6_8SWmI) | East Lancashire Railway crossing feed. |
| Williton crossing, Camera 2 | [YHILlgN9cFs](https://www.youtube.com/watch?v=YHILlgN9cFs) | West Somerset Railway level crossing. The WSR selector notes an 08:00–18:00 availability window. |
| Minehead Seaward Way crossing | [cO1MFjvfKUE](https://www.youtube.com/watch?v=cO1MFjvfKUE) | West Somerset Railway's Seaward crossing camera. |

The reproducible link list is `scripts/data/sammytv_crossing_cameras_2026-11-26.txt`. These are heritage railway cameras; an active camera does not mean trains are running continuously. Camera availability and stream IDs can change.

The authorised import ran on CXMS on 26 November: **four added, no failures**. Immediate server-side reads confirmed all four stored as **pending**, `is_live=true`, `live_camera=false`. No feed was approved or assigned to categories; existing approvals were preserved. Parent review links:

- [Ramsbottom north](https://www.cxms.fr/sammytv/admin/videos/794831e2-6f5c-4b1f-b397-b5fdf950ed07)
- [Townsend Fold](https://www.cxms.fr/sammytv/admin/videos/5f891ee2-acb5-4c83-86b9-2bb983208343)
- [Williton crossing](https://www.cxms.fr/sammytv/admin/videos/0a5ab908-41f1-4957-bd53-81099ecd3984)
- [Minehead Seaward Way crossing](https://www.cxms.fr/sammytv/admin/videos/d4818c3c-d7c3-48d6-9f01-79d9e459572b)

Live API checks on 26 November returned `privacyStatus=public`, `embeddable=true`, `liveBroadcastContent=live`, no age/region restrictions, `uploadStatus=uploaded` and `duration=P0D` for all four (also for Blue Anchor Camera 1 and Ford's Gaugemaster camera). This exposed an availability-check bug: the deployed code required `processed`, even for an ongoing live stream. The local fix accepts `uploaded` only for YouTube's explicitly confirmed live state. Contradictory end metadata stays unconfirmed; ordinary recordings still require processing. All existing privacy, age, region, creator binding, per-click recheck and explicit parent-camera approval controls remain in place. Four new regression tests pass as part of 130 SammyTV tests.

Deploy the upload-status fix before approving these feeds. Imports made by the previous adapter may retain `available=false`: use **Recheck video details**, choose **Live Cameras**, review the feed/operator and use **Approve as live camera**. Imports never approve or expose an unreviewed feed. No additional SQL is required.

## Independent hosting research

The non-YouTube sources below are research candidates, not approved or imported SammyTV feeds. Public viewing and permission to embed in another site are separate questions. Current SammyTV playback supports YouTube only; non-YouTube sources need a reviewed provider adapter and any required operator permission.

| Camera | Hosting evidence | Integration status |
| --- | --- | --- |
| [Wootton Station, Isle of Wight](https://camsecure.co.uk/wooton_station_isle_of_wight_webcam.html) | Camsecure's own page embeds a camsecure.uk player and explicitly identifies its streaming service. | Strong railway candidate. Owner/Camsecure permission and domain configuration required before embedding. |
| [Havenstreet, Isle of Wight Steam Railway](https://camsecure.co.uk/isle_of_wight_steam_railway_webcam.html) | Camsecure lists the railway as operator and its own hosting service. | Candidate only. Listing is older; current player availability needs checking. Same permission requirement. |
| [Nuremberg Airport: west and east apron](https://www.airport-nuernberg.de/de/webcam) | Airport privacy notice identifies Livespotting GmbH for webcam streams. Browser DOM showed two HTML5 video players rather than YouTube iframes. | Strong aircraft candidate. Official page says pictures are delayed and some flights temporarily suppress the feed. External embedding permission not established. |
| [Zurich Airport webcams](https://www.flughafen-zuerich.ch/en/passengers/experience/experiences/webcams) | Dock E Midfield Cam 1 embeds cam3.zurich-airport.com and identifies redics as its livecam provider. | Non-YouTube camera system, including controllable/single-frame views. Dock E camera displayed temporarily unavailable during inspection. Written framing/content permission required. |

Evidence and terms:

- [Camsecure fair usage](https://www.camsecure.co.uk/fair_usage_policy-camsecure_streaming.html): third-party hotlinking and direct player use are prohibited without permission; authorised multi-site options exist. Do not copy a discovered player/stream URL into SammyTV.
- [Nuremberg privacy notice, Livespotting section](https://www.airport-nuernberg.de/en/privacy-policy): webcam provider identified separately from the airport's ordinary YouTube videos.
- [Zurich terms](https://www.flughafen-zuerich.ch/en/passengers/general/terms/disclaimer): written approval required for framing and reuse of content.
- [SkylineWebcams FAQ](https://www.skylinewebcams.com/en/support/faq.html): third parties may use the supplied refreshing image embed (two-minute interval); full live video on external websites is limited to the camera owner. This could support a separate snapshots feature, not a general live-video source.

## Railway sites that still depend on YouTube

Direct browser checks of [Swanage Railway](https://www.swanagerailway.co.uk/webcams) and [KWVR](https://kwvr.co.uk/about-the-railway/webcams/) found youtube.com and youtube-nocookie.com players respectively. They are useful viewing sites but are not independent hosting alternatives. Older Railcam player links found on third-party directories are not evidence of current permission or current hosting.

## UK rules

The [government fact sheet updated 18 September 2026](https://www.gov.uk/government/publications/fact-sheet-new-rules-to-protect-children-online/fact-sheet-new-rules-to-protect-children-online) says first regulations are intended before the end of 2026, with implementation expected in spring 2027. It describes an under-16 social-media ban model including YouTube and restrictions on certain livestreaming/stranger-contact features on other services. Exact treatment of third-party embedded educational cameras cannot be concluded from this fact sheet. Independent hosting reduces dependency on YouTube; it is not evidence of exemption from future rules. Do not bypass age checks or platform restrictions.

## Implementation approach for a future provider

Approve one named camera from one operator, on a fixed HTTPS player host/path. Record the permission source and any domain restrictions. Review player controls, adverts, external links, recommendations, chat, cookies and outage behaviour before enabling it for a viewer. Use provider-specific validation and CSP allowlists; do not accept arbitrary iframe markup or stream URLs, proxy unknown remote content, or silently switch feeds. Keep snapshots visually distinct from live video. No provider outreach has been sent.
