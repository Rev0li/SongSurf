# API & Modules — SongSurf

---

## Backend Modules

### `SongSurf/server/app.py` — Flask Application

Entry point. Owns:
- Flask app configuration and secret management
- Route definitions for admin and guest APIs
- Download queue (`queue.Queue`) and worker thread
- Guest session registry (`dict` with TTL metadata)
- Auth decorators (`@login_required`, `@guest_required`)
- Watcher-mode vs. standalone-mode auth switching

**Auth logic:**
```
WATCHER_SECRET set → check X-Watcher-Token header only
WATCHER_SECRET not set → check Flask session cookie (standalone)
```

---

### `SongSurf/server/downloader.py` — YouTubeDownloader

**Class: `YouTubeDownloader(temp_dir, music_dir)`**

| Method | Description |
|---|---|
| `extract_metadata(url)` | Runs yt-dlp in info-only mode. Returns title, artist, album, year, thumbnail URL, duration, and `is_playlist`. Raises `ValueError` if duration exceeds `MAX_DURATION_SECONDS`. |
| `download_song(url, title, artist, album, year, output_dir)` | Downloads a single track to `temp_dir`, converts to MP3 via FFmpeg, returns the final `.mp3` path. |
| `download_playlist(url, output_dir, progress_callback)` | Downloads all tracks in a playlist sequentially. Calls `progress_callback(index, total, metadata)` per track. |
| `_find_ffmpeg()` | Auto-detects ffmpeg binary (checks `$PATH` and common install locations). |
| `_normalize_url(url)` | Strips tracking parameters, normalizes YouTube Music URLs. |

**Class: `DownloadProgress`**

Tracks live state (`percent`, `speed`, `eta`, `status`) updated via yt-dlp progress hook. Serialized by `to_dict()` and returned by `/api/status`.

---

### `SongSurf/server/organizer.py` — MusicOrganizer

**Class: `MusicOrganizer(music_dir)`**

| Method | Description |
|---|---|
| `organize(mp3_path, title, artist, album, year)` | Writes ID3 tags, detects featuring artists, moves file to `Artist/Album/Title.mp3` under `music_dir`. Returns final path. |
| `write_tags(path, title, artist, album, year, track)` | Writes ID3 tags using Mutagen. |
| `extract_featuring(title, artist)` | Parses `feat.` / `ft.` patterns from title; splits featuring artists into proper tag. Returns `(clean_title, full_artist)`. |
| `save_cover(mp3_path, image_url_or_bytes)` | Embeds album art in ID3 APIC frame and saves JPEG sidecar next to the MP3. |

---

### `watcher/watcher.py` — Watcher Proxy

**Flask app on port 8080.**

| Route | Method | Description |
|---|---|---|
| `/` | GET | Redirect based on session state (admin → loading, guest → loading, anon → login) |
| `/login` | GET / POST | Admin login form; sets session on success |
| `/guest/login` | GET / POST | Guest login form |
| `/logout` | GET | Clears admin session |
| `/guest/logout` | GET | Clears guest session |
| `/watcher/loading` | GET | Loading page; polls `/watcher/ready` |
| `/watcher/ready` | GET | Returns 200 when SongSurf is healthy, 503 while starting |
| `/<path:path>` | ANY | Catch-all proxy: validates session, starts SongSurf if needed, forwards request with `X-Watcher-Token` header |

**Inactivity logic:**
1. Every request updates `last_request_time`
2. Background thread checks every 60s
3. `last_request_time > INACTIVITY_TIMEOUT` → push warning to admin UI
4. `last_request_time > INACTIVITY_TIMEOUT + INACTIVITY_GRACE_TIMEOUT` → stop SongSurf container via Docker SDK

---

## HTTP API Reference (SongSurf)

All endpoints are JSON. Admin routes require a valid `X-Watcher-Token` header (or session cookie in standalone mode). Guest routes require a valid guest session cookie.

### Health

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/ping` | GET | None | Healthcheck — returns `{"status": "ok"}` |

---

### Admin — Extraction & Download

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/extract` | POST | Admin | Extract metadata from a YouTube Music URL |
| `/api/download` | POST | Admin | Queue a single-song download |
| `/api/download-playlist` | POST | Admin | Queue a full playlist/album download |
| `/api/cancel` | POST | Admin | Cancel the current download |
| `/api/status` | GET | Admin | Poll current download progress and queue state |

**`POST /api/extract` — request:**
```json
{ "url": "https://music.youtube.com/watch?v=..." }
```

**`POST /api/extract` — response:**
```json
{
  "success": true,
  "type": "song",
  "is_playlist": false,
  "metadata": {
    "title": "Blinding Lights",
    "artist": "The Weeknd",
    "album": "After Hours",
    "year": "2019",
    "url": "https://...",
    "thumbnail": "https://...",
    "duration": 200
  }
}
```

**`POST /api/download` — request:**
```json
{
  "url": "https://music.youtube.com/watch?v=...",
  "title": "Blinding Lights",
  "artist": "The Weeknd",
  "album": "After Hours",
  "year": "2019"
}
```

**`GET /api/status` — response:**
```json
{
  "in_progress": true,
  "current_download": { "title": "Blinding Lights", "artist": "The Weeknd" },
  "progress": { "percent": 67, "speed": "812 KB/s", "eta": "8s", "status": "downloading" },
  "queue_size": 2,
  "batch_active": false,
  "batch_total": 0,
  "batch_done": 0,
  "batch_percent": 0,
  "error": null
}
```

---

### Admin — Library Management

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/library` | GET | Admin | Returns folder tree of `/data/music` |
| `/api/library/move` | POST | Admin | Move a song to a different folder |
| `/api/library/rename-folder` | POST | Admin | Rename a folder |
| `/api/library/upload-image` | POST | Admin | Upload custom album art for a folder |
| `/api/library/folder-cover` | GET | Admin | Get album art for a folder |
| `/api/admin/prepare-zip` | POST | Admin | Package admin library as a ZIP |
| `/api/prefetch/cancel` | POST | Admin | Cancel background prefetch |
| `/api/prefetch/cover` | GET | Admin | Get prefetched cover art for preview |

---

### Guest — Extraction & Download

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/guest/extract` | POST | Guest | Extract metadata (same as admin, restricted URLs) |
| `/api/guest/download` | POST | Guest | Queue single-song download (quota-checked) |
| `/api/guest/download-playlist` | POST | Guest | Queue playlist (quota-checked) |
| `/api/guest/cancel` | POST | Guest | Cancel current download |
| `/api/guest/status` | GET | Guest | Poll download progress + session state |
| `/api/guest/prepare-zip` | POST | Guest | Package guest session files as ZIP |
| `/api/guest/extend-session` | POST | Guest | Add time to session TTL |

**`GET /api/guest/status` — response:**
```json
{
  "in_progress": false,
  "session_remaining_seconds": 2847,
  "warn_threshold": 300,
  "quota_used": 3,
  "quota_max": 10,
  "downloads": [
    { "title": "Blinding Lights", "artist": "The Weeknd", "status": "completed" }
  ],
  "progress": { "percent": 100, "status": "completed" },
  "error": null
}
```

---

## Frontend JS API Client (`frontend/src/lib/api.js`)

Thin wrapper around `fetch`. All methods return parsed JSON or throw on non-2xx responses.

### Admin methods

```js
api.getStatus()                          // → /api/status
api.extractMetadata(url)                 // → POST /api/extract
api.download(url, metadata)              // → POST /api/download
api.downloadPlaylist(url, metadata)      // → POST /api/download-playlist
api.cancel()                             // → POST /api/cancel
api.getLibrary()                         // → GET /api/library
api.moveFile(src, dest)                  // → POST /api/library/move
api.renameFolder(path, name)             // → POST /api/library/rename-folder
api.uploadCover(formData)                // → POST /api/library/upload-image
api.prepareAdminZip()                    // → POST /api/admin/prepare-zip
api.cancelPrefetch()                     // → POST /api/prefetch/cancel
```

### Guest methods

```js
api.getGuestStatus()                     // → GET /api/guest/status
api.guestExtractMetadata(url)            // → POST /api/guest/extract
api.guestDownload(url, metadata)         // → POST /api/guest/download
api.guestDownloadPlaylist(url, metadata) // → POST /api/guest/download-playlist
api.guestCancel()                        // → POST /api/guest/cancel
api.guestPrepareZip()                    // → POST /api/guest/prepare-zip
api.extendGuestSession()                 // → POST /api/guest/extend-session
```

### Low-level helpers

```js
api.get('/api/custom-endpoint')
api.post('/api/custom', { key: 'value' })
```

---

## Guest Session Model

Each guest session is an entry in the in-memory `guest_sessions` dict:

```python
guest_sessions[session_id] = {
    "created_at": datetime,
    "expires_at": datetime,
    "songs_downloaded": int,
    "downloads": [],          # list of completed download metadata
    "music_dir": Path,        # /data/music_guest/<session_id>/
    "temp_dir": Path,         # /data/temp_guest/<session_id>/
    "zip_path": Path | None,  # set after prepare-zip
    "cleanup_after": datetime | None  # set after ZIP, delayed 120s
}
```

Session state is not persisted to disk — a container restart invalidates all active guest sessions.

---

## Docker Service Contracts

### Healthchecks

| Service | Command | Interval | Start period |
|---|---|---|---|
| Watcher | `curl -f http://localhost:8080/ping` | 30s | 10s |
| SongSurf | `curl -f http://localhost:8081/ping` | 10s | 15s |

### Volume Mounts

| Host path | Container path | Service |
|---|---|---|
| `./data/music` | `/data/music` | SongSurf |
| `./data/music_guest` | `/data/music_guest` | SongSurf |
| `./data/temp` | `/data/temp` | SongSurf |
| `./data/temp_guest` | `/data/temp_guest` | SongSurf |
| `./logs` | `/app/logs` | SongSurf |
| `/var/run/docker.sock` | `/var/run/docker.sock` | Watcher (Docker SDK) |
