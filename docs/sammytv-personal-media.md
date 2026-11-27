# SammyTV: personal media and finding alternatives

Exploration, 27 November 2026. No personal media has been accessed or uploaded, no videos imported, and this document does not implement the feature.

## Proposed first version: My videos & photos

Add a device-only gallery to the existing signed-in experience. A “Choose from this device” button opens the system file/photo picker. Selected photos appear as cards and selected videos play with native controls on the same gallery page. The gallery must not contain an upload form or send selected files, filenames, frames or metadata to the server. Keep parent-approved internet videos in the existing catalogue and distinguish personal media clearly.

Use selected `File` objects and `URL.createObjectURL()`, not base64 encoding or reading an entire large file into an ArrayBuffer. Keep references in memory for this page; do not persist full video/photo blobs to IndexedDB, Cache Storage or the origin private file system. Do not write another permanent copy of a long recording. The operating system may still prepare a temporary export, convert a format or download an iCloud-only item during selection. Those are device/cloud-provider operations, not SammyTV server storage.

For a video thumbnail, read metadata, seek to one frame within the duration and draw a small preview locally. Choose one random timestamp per selection, with an option to use the current frame, rather than continuously seeking or analysing the whole recording. Generate previews serially, impose a short timeout, and use an icon if decoding fails. Release object URLs and media decoders when no longer needed. Photos can display their selected local image. Test actual MOV/HEVC, MP4, HEIC, large recordings and cloud-only assets on Sammy's device; support depends on the browser and codec, not just the extension. No server transcoding is planned.

This removes hosted-media storage and streaming costs for personal files. It does not remove device memory, battery, decoding time, or any existing iCloud storage/download charges. Do not automatically reject a long recording just because it is long; allow playback while thumbnail generation fails gracefully.

## The persistence limitation

| Approach | Reopening favourites | Storage implications |
| --- | --- | --- |
| Standard web file/photo picker | Selected files must generally be picked again after a page reload or leaving the gallery. Keep viewing within the gallery page during the session. | No SammyTV server media storage; no app-managed permanent media copy. |
| File System Access where supported | Remember a file/directory handle locally and request permission again when required. Feature-detect and provide the standard picker fallback. | Store references, not whole files. Not a Safari/iOS Photos-library solution. |
| Later iPhone app using Photos APIs | Use permitted Photos assets and native identifiers, handling limited access, revoked permissions, deletion and cloud-only assets. | Can avoid our cloud media storage; device/iCloud behaviour still applies. |

A `blob:` URL cannot be saved as a permanent or cross-device favourite. A filename, `file://` path or pasted Photos share link is not a durable browser permission to read a local asset. An installed website does not gain native Photos access merely by being installed. Do not promise a seamless permanent camera-roll library in the first web version.

Recommend the session-only web prototype first, tested on Sammy's actual device. If reselecting files makes it frustrating, move the personal gallery to a small native app rather than copying gigabytes into browser storage. Optional saved titles/small thumbnails would stay on that device, scoped to the signed-in profile with clear/delete controls; they would still not restore Safari access to the original file. Default the prototype to no persistence, clear selected personal media on sign-out, and do not add file details to analytics or shared family database rows.

## Free sources outside YouTube

Prioritise independently hosted, specifically licensed files, with parent review and attribution. Free licensing does not guarantee free permanent hosting, embeddability, device compatibility, or the availability of the same creator's videos elsewhere. Do not substitute another social video platform as a presumed exemption from UK rules.

- **Wikimedia Commons:** a concrete candidate is [Railway Crossing In Action with Train Passing Through](https://commons.wikimedia.org/wiki/File:Railway_Crossing_In_Action_with_Train_Passing_Through.webm), 56 seconds at the Oxley Highway crossing near Wauchope, Australia. The file is identified as WeenyBeany's own work under CC BY 4.0. Review suitability and playback before importing; preserve creator/source/licence attribution. Commons allows direct linking subject to licence conditions, but warns that remote assets can change or disappear. A fixed reviewed source plus an unavailable state is needed.
- **NASA:** look for appropriate aviation/space media under its media-usage guidelines, checking each asset for third-party credits. Do not assume every item on a NASA page is unrestricted or hosted outside YouTube.
- **Pexels:** useful for freely licensed stock clips rather than guaranteed full-length replacements. Its licence and API terms differ; check integration eligibility, credits, hosting conditions and API-key availability before planning an automated importer. Do not promise a free API integration based solely on its free download licence.

The provider adapter/migration in the [transition plan](sammytv-provider-transition.md) is still required for remote non-YouTube playback. Direct-linking a reviewed third-party asset can avoid our own media hosting bill, but has reliability and licensing tradeoffs. Personal local-file playback is a separate source and should not be uploaded into that remote catalogue.

## Similar-video and reverse searches

For finding another copy or the source of a public clip, Google's image search/Lens can search a distinctive screenshot or public thumbnail. Results may find matching scenes or pages; they do not establish permission to reuse a found copy. Lens also has video-understanding features for asking questions about moving objects, which is different from a guaranteed whole-web duplicate-video index.

For finding different clips on the same topic, creator/title/location/train-class metadata is a useful first step. A future parent-only “Find alternatives” flow could assemble targeted searches from approved metadata, let the parent compare candidates and send selected results to review. It must not auto-approve matches, scrape YouTube downloads, or send Sammy's personal photos/video frames to an external search or AI service. Keep personal media and external discovery separate.

## Sources checked

- [MDN: using selected files and object URLs](https://developer.mozilla.org/en-US/docs/Web/API/File_API/Using_files_from_web_applications).
- [Chrome: File System Access and remembered handles](https://developer.chrome.com/docs/capabilities/web-apis/file-system-access).
- [Web-platform compatibility: File System Access](https://web-platform-dx.github.io/web-features-explorer/features/file-system-access/).
- [Apple: selecting Photos assets](https://developer.apple.com/documentation/photokit/selecting-photos-and-videos-in-ios).
- [Commons: direct linking and reuse](https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia/technical).
- [NASA media-usage guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/).
- [Pexels licence](https://www.pexels.com/license/) and [API information](https://www.pexels.com/api/).
- [Google: image search](https://support.google.com/websearch/answer/1325808) and [Lens video understanding](https://blog.google/products-and-platforms/products/search/google-search-lens-october-2024-updates/).
