# API & Modules — SongSurf

Reference generated from the current code (`server/app.py`, `server/state_store.py`, `server/downloader.py`, `server/organizer.py`, `watcher/watcher.py`). All endpoints return JSON unless noted.

**Auth:** every `/api/*` route requires the Watcher-injected `X-Watcher-Token` header (`@auth_required`). The user identity comes from `X-User-Id` / `X-User-Role` / `X-User-Email`. In `DEV_MODE` (no `WATCHER_SECRET`) a local admin dev user is injected.

---

## SongSurf HTTP API

### Health & identity

| Endpoint | Method | Description |
|---|---|---|
| `/ping` | GET | Healthcheck (no auth) — used by Watcher and Docker healthcheck |
| `/api/me` | GET | `{sub, uid, role, email, pseudo}` of the current user (`pseudo` = exact portal pseudo, shown in the header; `uid` = portal UUID, the storage key) |
| `/api/status` | GET | Download progress, queue size, batch progress, caller's daily counter, `is_mine`, `worker`. Watcher probe (valid `X-Watcher-Token`, no identity) → only `{in_progress, queue_size}` |

**`GET /api/status` — response:**
```json
{
  "in_progress": true,
  "current_download": { "url": "…", "metadata": {…}, "user_key": "…", "user_pseudo": "…", "started_at": "…" },
  "progress": { "percent": 67, "phase": "downloading", "speed": "812 KB/s", "eta": "8s" },
  "queue_size": 2,
  "batch_active": true, "batch_total": 12, "batch_done": 4, "batch_percent": 38.5,
  "daily_count": 7, "daily_limit": 50,
  "is_mine": true,
  "worker": { "songs_before_mine": null, "owner": null, "current": null },
  "pending": [ { "artist": "…", "title": "…", "album": "…" } ],
  "last_completed": {…}, "last_error": null,
  "cookies_present": true, "cookies_age_days": 0.4
}
```
`last_completed` / `last_error` / `cookies_*` / `daily_*` / `pending` are the **caller's own**; `daily_limit` is `0` (unlimited) for the admin. `current_download` is `null` when the worker is busy with another member's song (`is_mine: false`); `worker` then says who uses it: `songs_before_mine` = songs that start before the caller's next one (current song included, `null` if the caller has nothing queued); `owner` (pseudo) and `current` (`{artist, title}`) are filled **for the admin only**.
`queue_size` = songs queued but not started, all users.
Phases: `downloading` (0–50 weighted) → `converting` (55) → `organizing` (90) → `completed` (100).

### Extraction & download

| Endpoint | Method | Description |
|---|---|---|
| `/api/extract` | POST | `{url}` → metadata. Single song: flattened fields + `is_playlist: false`. Album/playlist: `{type, title, artist, year, thumbnail_url, thumbnail_candidates, songs[], total_songs, total_duration, is_playlist: true}` |
| `/api/download` | POST | Queue one song (= a one-song job). Body: `{url, title, artist, album, year, track_number, album_artist, artists[]}`. 429 only if the caller already has `MAX_PENDING_JOBS` (100) jobs queued or reached their daily limit (`code: 'daily_limit'`, members only) — several downloads can be queued at once |
| `/api/download-playlist` | POST | Queue a whole album as one job. Body: `{playlist_metadata: {title, artist, year, songs[]}}` — each song keeps its own `artists` and `track_number`; album-level artist becomes `TPE2`. Returns `{added, total, queue_size}` (`queue_size` = songs queued but not yet started) |

Songs in playlist extraction carry: `{title, artist, artists[], url, id, duration, track_number}`.

### ZIP export

| Endpoint | Method | Description |
|---|---|---|
| `/api/prepare-zip` | POST | Starts building the ZIP of the user's whole library in the background → 202 `{status: 'building', done: 0, total}` (already building → same answer, no second build). No MP3 → 404. Admin library: 403 `{code: 'zip_disabled'}` (SSF-10) |
| `/api/zip-status` | GET | `{status: 'idle' \| 'building' \| 'ready' \| 'error', done, total, count, size_mb, download_url?, error?}` — the frontend polls it every second. State persisted in SQLite: a ready ZIP survives a restart, a build cut by a restart becomes `error` |
| `/api/download-zip` | GET | Streams the ZIP once `ready` (otherwise 404). **Member libraries are deleted once the whole file has been sent**; an interrupted download keeps the library and the `ready` ZIP (SSF-14). Admin library: 403 `zip_disabled`, never exported nor deleted (role, music root and mount points checked) |

### Library

| Endpoint | Method | Description |
|---|---|---|
| `/api/library` | GET | Tree: `{artists: [{name, path, albums: [{name, path, songs[]}], has_picture}], playlists: [...]}` (flat folders = legacy) |
| `/api/library/move` | POST | `{source, target_folder}` — move one MP3; re-syncs TPE1/TALB to the new folder position |
| `/api/library/move-folder` | POST | `{folder_path, new_parent}` — move an album to another artist (merges if it exists) |
| `/api/library/delete-folder` | POST | **Admin only** (403 otherwise). `{folder_path}` — permanently delete an artist or album folder (`shutil.rmtree`); an artist folder left empty after an album deletion is removed too. Returns `{deleted_songs}`. The library root itself is rejected |
| `/api/library/folder-cover` | GET | `?folder_path=` → cover image (cover/folder/artist.*, falls back to embedded APIC). The APIC extraction is persisted as `cover.jpg` in the album folder (JPEG-converted, atomic write) so the MP3 is only parsed once. Sends `Cache-Control: private, max-age=86400` — safe because the frontend versions image URLs (`?t=<version>`, bumped only on cover upload) |
| `/api/library/artist-picture` | GET | `?folder_path=` → artist picture (folder.* / artist.*). Same `Cache-Control: private, max-age=86400` |

### Metadata editor

| Endpoint | Method | Description |
|---|---|---|
| `/api/library/song-meta` | GET | `?path=` → full dump: file info, audio info (duration, bitrate…), all ID3 frames (multi-value frames joined with `"; "`), custom TXXX tags, cover presence |
| `/api/library/song-meta/save` | POST | `{path, tags: {title, artist, album_artist, album, year, track_number, disc_number, genre, composer, copyright, publisher, bpm, key, language, isrc, encoded_by, comment}}` — empty value deletes the frame. **`artist`, `genre`, `composer` accept `;`-separated input → written as real ID3v2.4 multi-value frames. `album_artist` stays single-value (Jellyfin grouping key)** |
| `/api/library/album-tracks` | GET | `?folder_path=` → lightweight tracklist `[{path, name, title, track_number}]` (powers the album panel TRCK display and the "Numéroter les pistes" reorder mode) |
| `/api/library/album-status` | GET | `?folder_path=<artist>` → per-album tag completeness `[{path, name, tracks, missing: {genre, year, track_number}, genres: [distinct TCON values], complete}]` (powers the artist-view badges + prefills the artist genre field) |
| `/api/library/renumber-album` | POST | `{folder_path, paths: [ordered]}` → writes TRCK `i/total` on the whole album. `paths` must cover every MP3 of the folder exactly once |
| `/api/library/set-artist-genre` | POST | `{folder_path: <artist>, genre}` → overwrites TCON on every MP3 under the artist folder (all albums, recursive). `genre` accepts `;`-separated multi-values → `{updated, errors[]}` |
| `/api/library/song-cover/upload` | POST | form `path` + `image` → embeds APIC + writes `cover.jpg` |
| `/api/library/album-cover/upload` | POST | form `folder_path` + `image` → `cover.jpg` only |
| `/api/library/artist-cover/upload` | POST | form `folder_path` + `image` → `folder.jpg` |
| `/api/library/audit/artist` | GET | **All members** (operates on the caller's own library). `?path=<artist folder>` → metadata audit report: per-album iTunes comparison (genre, year, album artist, track numbers, TPE1/TPE2 coherence) with actionable `recommendations` (`{id, field, proposed, current, reason, changes: [{path, value}]}`) and informational `warnings`. Missing TRCK values are matched against the official iTunes tracklist (unambiguous title matches only). Nothing is written |
| `/api/library/audit/apply` | POST | **All members.** `{changes: [{path, field, value}]}` → writes the approved recommendations via the shared ID3 writer → `{applied, errors[]}` |

### Admin-only

| Endpoint | Method | Description |
|---|---|---|
| `/api/admin/dl-logs` | GET | `?pseudo=&limit=` → parsed download log entries (403 for non-admin) |
| `/api/admin/extract-covers` | POST | `{overwrite}` → backfill `cover.jpg` across the whole library |
| `/api/admin/genre-backfill` | POST | Starts a background thread that fills missing TCON across the whole admin library via iTunes lookups (409 if already running). No UI button — the per-artist audit covers genres; kept for curl/automation |
| `/api/admin/genre-backfill/status` | GET | `{status: idle\|running\|done\|error, total, done, updated, failed, last_file}` |

### Browser extension

| Endpoint | Method | Description |
|---|---|---|
| `/api/queue-direct` | POST | `{url, artist?, album?, title?, year?}` → fire-and-forget: spawns a thread that extracts metadata then enqueues server-side (`_queue_direct_async`). Returns immediately; downloads even with no SongSurf tab open. Same 429 rules as `/api/download` (queue full, daily limit) |
| `/api/preview` | POST | `{url}` → lightweight metadata (no side-effect) for the extension's confirmation UI |
| `/api/cookies/update` | POST | `{cookies}` (Netscape format, validated) → written to `/data/cookies/<uid>.txt` (chmod 600) → `{success, count, pseudo}` |

---

## Watcher HTTP surface

| Route | Method | Description |
|---|---|---|
| `/ping` | GET | Watcher healthcheck |
| `/watcher/loading` | GET | Loading page while SongSurf boots |
| `/watcher/ready` | GET | 200 when SongSurf answers `/ping`, 503 while starting |
| `/watcher/inactivity-status` | GET | `{idle_seconds, warned}` for the frontend banner |
| `/watcher/keepalive` | POST | Resets the inactivity timer (requires auth) |
| `/logout` | GET/POST | Puts SongSurf to sleep (unless busy), redirects to `REVAUTH_HOME_URL` (portal session, no cookie here) |
| `/<any>` | ANY | Catch-all: portal gate (no valid proof → 401 JSON for API/extension, 401 « passe par le portail » page otherwise) → start container if needed → proxy with injected headers. API callers get JSON 503 `{retry: true}` while SongSurf boots |
| `OPTIONS *` | OPTIONS | CORS preflight — only the SongSurf Clip extension origin (`chrome-extension://<SONGSURF_EXTENSION_ID>`), 403 otherwise |

---

## Backend modules

### `server/state_store.py` — `StateStore(db_path)` (SSF-03)

SQLite (`/data/state/songsurf.db`, WAL), one connection behind a lock. At open, a song left `active` goes back to `pending` and a ZIP left `building` becomes `error` (interrupted).

| Method | Description |
|---|---|
| `enqueue_job(user_key, songs)` | One job (album or single song) = its songs as `pending` rows, in order |
| `claim_next()` / `finish(id)` | Next song in round-robin order, marked `active` (pointer `rr_last_user` persisted) / removed once processed (success or failure) |
| `pending_jobs(user_key)` · `pending_count()` · `pending_for(user_key)` · `songs_before(user_key)` | Per-user job count (queue limit), global pending songs, caller's pending songs, songs passing before the caller's next one |
| `daily_count(user_key, day)` / `daily_increment(user_key, day)` | Per-user daily counter (older days purged) |
| `zip_get` / `zip_set` / `zip_delete` | Per-user ZIP export state (`building` → `ready` / `error`) |

`round_robin_order(items, last_user)` (pure) — users rotate in key order starting after the last served one; each user's songs keep their arrival order.

### `server/downloader.py` — `YouTubeDownloader(temp_dir, music_dir)`

| Method | Description |
|---|---|
| `extract_metadata(url)` | Info-only yt-dlp run → `{title, artist, artists[], album_artist, album, year, track_number, thumbnail_url, thumbnail_candidates[], duration, view_count}`. Raises on duration > `MAX_DURATION_SECONDS` |
| `extract_playlist_metadata(url)` | `extract_flat` run → playlist metadata + per-song list (see API above). Artist fallbacks: album_artist → artist → first song → title pattern |
| `download(url, metadata)` | bestaudio → MP3 (FFmpeg `preferredquality 0`), staged in temp, cache-aware (reuses an existing temp file) |
| `get_progress()` | Serialized `DownloadProgress` state |
| `_artist_list(info_artists, fallback)` / `_split_artists(s)` | Artist list normalization (yt-dlp list preferred; split on `&`/`,`/`et`/`and`/`/`; strips ` - Topic`; deduped) |
| `_primary_artist(s)` | First artist of the list (names the folder) |
| `_detect_type(url)` | `'song'` / `'playlist'` from URL shape (`v=`, `list=`, `/browse/`) |
| `_cookies_opts(cookiefile)` | Adds the owner's `cookiefile` when it exists (passed by `extract_metadata` / `extract_playlist_metadata` / `download`) |

`DownloadProgress` — percent/speed/eta/phase updated by the yt-dlp progress hook.

### `server/organizer.py` — `MusicOrganizer(music_dir)`

| Method | Description |
|---|---|
| `organize(file_path, metadata)` | Featuring detection → `Artist/Album/Title.mp3` placement (duplicate-safe) → `_update_tags` → `cover.jpg`. `metadata`: `{artist, artists[], album_artist, album, title, year, track_number, track_total}` |
| `detect_featuring(title, artist)` | Parses `feat./ft./featuring` patterns → `{main_artist, feat_artists[], clean_title, has_feat}` |
| `_update_tags(path, tags, thumbnail)` | Mutagen: TIT2, **TPE1 multi-value**, **TPE2 (album_artist or primary artist, always set)**, TALB, TDRC, **TRCK `n/total`**, APIC (cropped/resized JPEG) |
| `extract_album_covers(overwrite)` | Backfills `cover.jpg` per album (sidecar → APIC → FFmpeg frame fallbacks) |

### `server/genre_lookup.py`

| Function | Description |
|---|---|
| `lookup_genres(artist, title, album)` | iTunes Search (FR + US storefronts) → deduped genre list for a song; per-album memory cache; silent failure (`[]`) |
| `lookup_album_info(artist, album)` | iTunes album search (FR + US) → `{found, genres[], year, album_artist, track_count, collection_id}` for the audit; same contract (cache, never raises) |
| `lookup_album_tracks(collection_id)` | iTunes lookup by `collectionId` → official tracklist `[{title, track_number, track_count}]` sorted by track number; cached, never raises |

### `server/library_audit.py`

| Function | Description |
|---|---|
| `audit_artist(artist_dir, music_dir, album_lookup=, track_lookup=)` | Full report for one artist: per-album recommendations (genre/year/album_artist/artist/track_number, each a checkable diff) + warnings (TPE1/TPE2 mismatch, duplicate track numbers, missing covers, incomplete album vs iTunes). Missing TRCK → unambiguous title match against the iTunes tracklist (`_match_missing_tracks`, feat-suffixes stripped). Reads via `mutagen.id3.ID3` |
| `backfill_genres(music_dir, state, lock, genre_lookup_fn=)` | Background worker: writes missing TCON across the library (tags first, folder names as fallback), updates the shared progress `state` under `lock` |

### `watcher/watcher.py`

| Function | Description |
|---|---|
| `_user_from_proxy_headers()` | Portal gate: `X-Proxy-Token` vs `SONGSURF_PROXY_SECRET` (constant-time) → `{sub: X-User-Name, role, email: '', uid: X-User-Id}`, else `None` |
| `_get_user_from_request()` | `DEV_MODE` → dev user; else `_user_from_proxy_headers()` |
| `_proxy(user)` | Drops client `X-User-*` / `X-Proxy-Token`, forwards with `X-Watcher-Token` + `X-User-Id/Role/Email` (+ `X-User-Portal-Id`); starts container when down |
| `_inactivity_watcher()` | Background thread: warn → grace → `container.stop()` |

---

## Frontend API client (`frontend/src/lib/api.js`)

```js
api.me()                                   // GET  /api/me
api.getStatus()                            // GET  /api/status
api.extract(url)                           // POST /api/extract
api.download(payload)                      // POST /api/download
api.downloadPlaylist(payload)              // POST /api/download-playlist
api.prepareZip()                           // POST /api/prepare-zip (202, build in background)
api.zipStatus()                            // GET  /api/zip-status
api.getLibrary()                           // GET  /api/library
api.moveSong(source, targetFolder)         // POST /api/library/move
api.moveFolder(folderPath, newParent)      // POST /api/library/move-folder
api.deleteFolder(folderPath)               // POST /api/library/delete-folder (admin)
api.songMeta(path)                         // GET  /api/library/song-meta
api.saveSongMeta(path, tags)               // POST /api/library/song-meta/save
api.albumTracks(folderPath)                // GET  /api/library/album-tracks
api.albumStatus(folderPath)                // GET  /api/library/album-status
api.renumberAlbum(folderPath, paths)       // POST /api/library/renumber-album
api.setArtistGenre(folderPath, genre)      // POST /api/library/set-artist-genre
api.uploadSongCover(path, file)            // POST /api/library/song-cover/upload
api.uploadAlbumCover(folderPath, file)     // POST /api/library/album-cover/upload
api.uploadArtistCover(folderPath, file)    // POST /api/library/artist-cover/upload
api.getFolderCoverUrl(folderPath, ts)      // GET  /api/library/folder-cover (URL builder — ts = stable per-path version, NOT Date.now())
api.getArtistPictureUrl(folderPath, ts)    // GET  /api/library/artist-picture (URL builder — same versioning)
api.auditArtist(path)                      // GET  /api/library/audit/artist
api.auditApply(changes)                    // POST /api/library/audit/apply
api.genreBackfillStart()                   // POST /api/admin/genre-backfill
api.genreBackfillStatus()                  // GET  /api/admin/genre-backfill/status
```

---

## Docker service contracts

### Volumes (SongSurf)

| Host | Container | Purpose |
|---|---|---|
| `./data/music` | `/data/music` | Libraries (per-user subfolders in prod) |
| `./data/temp` | `/data/temp` | Download staging + ZIP staging |
| `./logs` | `/app/logs` | `activity.log`, `downloads.log` |

Watcher mounts `/var/run/docker.sock` for container lifecycle.

### Healthchecks

Both services expose `/ping`; Compose healthchecks poll them (Watcher gates SongSurf readiness on it too).
