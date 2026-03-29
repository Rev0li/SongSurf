#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
downloader.py - Module de téléchargement avec yt-dlp

FONCTIONNALITÉ:
  - Télécharge les vidéos YouTube en MP3 via yt-dlp
  - Gestion de la progression en temps réel
  - Conversion automatique en MP3 (via FFmpeg)
  - Gestion des erreurs robuste
"""

import yt_dlp
from pathlib import Path
import os
import re
import shutil
from datetime import datetime
import logging

logger = logging.getLogger('songsurf')


class DownloadProgress:
    """Classe pour suivre la progression du téléchargement"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.percent    = 0
        self.downloaded = 0
        self.total      = 0
        self.speed      = "0 KB/s"
        self.eta        = "0s"
        self.status     = "idle"  # idle, downloading, processing, completed, error

    def update(self, d):
        """Callback appelé par yt-dlp pour mettre à jour la progression"""
        if d['status'] == 'downloading':
            self.status     = 'downloading'
            self.downloaded = d.get('downloaded_bytes', 0)
            self.total      = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
            if self.total > 0:
                self.percent = int((self.downloaded / self.total) * 100)
            speed = d.get('speed', 0)
            if speed:
                self.speed = f"{speed / 1024:.0f} KB/s"
            eta = d.get('eta', 0)
            if eta:
                self.eta = f"{eta}s"
        elif d['status'] == 'finished':
            self.status  = 'processing'
            self.percent = 100

    def to_dict(self):
        return {
            'status':     self.status,
            'percent':    self.percent,
            'downloaded': self.downloaded,
            'total':      self.total,
            'speed':      self.speed,
            'eta':        self.eta
        }


class YouTubeDownloader:
    """Téléchargeur YouTube avec yt-dlp"""

    def __init__(self, temp_dir, music_dir):
        self.temp_dir  = Path(temp_dir)
        self.music_dir = Path(music_dir)
        self.progress  = DownloadProgress()
        self.temp_dir.mkdir(exist_ok=True, parents=True)
        self.music_dir.mkdir(exist_ok=True, parents=True)
        self.ffmpeg_location = self._find_ffmpeg()

    # ──────────────────────────────────────────────────────────────
    # Téléchargement
    # ──────────────────────────────────────────────────────────────

    def download(self, url, metadata):
        """
        Télécharge une vidéo YouTube en MP3.

        Args:
            url (str): URL YouTube ou YouTube Music
            metadata (dict): {artist, album, title, year}

        Returns:
            dict: {success, file_path, error}
        """
        try:
            logger.info(f"⬇️  Téléchargement: {metadata.get('title', 'Unknown')}")

            # Convertir l'URL YouTube Music → YouTube classique
            url = self._normalize_url(url)
            logger.info(f"   URL: {url}")

            self.progress.reset()
            self.progress.status = 'downloading'

            temp_filename = self._clean_filename(
                f"{metadata.get('artist', 'Unknown')} - {metadata.get('title', 'Unknown')}"
            )

            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '0',
                }],
                'outtmpl':          str(self.temp_dir / f'{temp_filename}.%(ext)s'),
                'quiet':            True,
                'no_warnings':      True,
                'progress_hooks':   [self.progress.update],
                'noplaylist':       True,
                'writethumbnail':   True,
                'nocheckcertificate': True,
            }

            if self.ffmpeg_location:
                ydl_opts['ffmpeg_location'] = self.ffmpeg_location

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)

            downloaded_file = self.temp_dir / f"{temp_filename}.mp3"
            if not downloaded_file.exists():
                raise FileNotFoundError(f"Fichier MP3 introuvable après conversion: {downloaded_file}")

            self.progress.status  = 'completed'
            self.progress.percent = 100
            logger.info(f"   ✅ Téléchargé: {downloaded_file.name}")

            return {
                'success':   True,
                'file_path': str(downloaded_file),
                'metadata':  metadata,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Téléchargement échoué: {e}")
            self.progress.status = 'error'
            return {
                'success':   False,
                'error':     str(e),
                'timestamp': datetime.now().isoformat()
            }

    def get_progress(self):
        """Retourne la progression actuelle"""
        return self.progress.to_dict()

    # ──────────────────────────────────────────────────────────────
    # Extraction de métadonnées
    # ──────────────────────────────────────────────────────────────

    def extract_metadata(self, url):
        """
        Extrait les métadonnées d'une vidéo YouTube sans la télécharger.

        Returns:
            dict: {success, metadata: {title, artist, album, year, thumbnail_url}, error}
        """
        try:
            url = self._normalize_url(url)
            logger.info(f"🔍 Extraction métadonnées: {url}")

            ydl_opts = {
                'quiet':         True,
                'no_warnings':   True,
                'skip_download': True,
                'noplaylist':    True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            title    = info.get('title', 'Unknown Title')
            uploader = info.get('uploader', 'Unknown Artist')
            artist   = info.get('artist') or info.get('creator') or uploader
            album    = info.get('album', 'Unknown Album')

            release_date = info.get('release_date') or info.get('upload_date', '')
            year = release_date[:4] if len(release_date) >= 4 else ''

            if artist.endswith(' - Topic'):
                artist = artist[:-8]

            metadata = {
                'title':         title,
                'artist':        artist,
                'album':         album,
                'year':          year,
                'thumbnail_url': info.get('thumbnail', ''),
                'duration':      info.get('duration', 0),
                'view_count':    info.get('view_count', 0)
            }

            logger.info(f"   ✅ {artist} — {title} ({album}, {year})")
            return {'success': True, 'metadata': metadata, 'timestamp': datetime.now().isoformat()}

        except Exception as e:
            logger.error(f"❌ Extraction métadonnées: {e}")
            return {'success': False, 'error': str(e), 'timestamp': datetime.now().isoformat()}

    def extract_playlist_metadata(self, url):
        """
        Extrait les métadonnées d'un album ou playlist YouTube Music.

        Returns:
            dict: {success, type, title, artist, songs: [{title, artist, url, duration}], ...}
        """
        try:
            logger.info(f"💿 Extraction playlist: {url}")

            ydl_opts = {
                'quiet':          True,
                'no_warnings':    True,
                'skip_download':  True,
                'extract_flat':   'in_playlist',
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if 'entries' not in info:
                return {'success': False, 'error': 'URL ne contient pas de playlist/album'}

            playlist_type  = 'album' if 'browse' in url else 'playlist'
            playlist_title = info.get('title', 'Unknown Playlist')

            if playlist_title.startswith('Album - '):
                playlist_title = playlist_title[8:]

            playlist_artist = (
                info.get('artist') or info.get('creator') or
                info.get('uploader') or info.get('channel')
            )
            if playlist_artist and playlist_artist.endswith(' - Topic'):
                playlist_artist = playlist_artist[:-8]

            playlist_year = ''

            # Fallback : extraire l'artiste depuis la première chanson
            if not playlist_artist or str(playlist_artist).lower() in ('none', ''):
                logger.info("   🔍 Artiste non trouvé, extraction depuis la première chanson…")
                first_entry = info['entries'][0] if info['entries'] else None
                if first_entry and first_entry.get('id'):
                    try:
                        first_song_url  = f"https://www.youtube.com/watch?v={first_entry['id']}"
                        first_song_info = self.extract_metadata(first_song_url)
                        if first_song_info['success']:
                            playlist_artist = first_song_info['metadata'].get('artist', 'Unknown Artist')
                            playlist_year   = first_song_info['metadata'].get('year', '')
                            logger.info(f"   ✅ Artiste via première chanson: {playlist_artist}")
                    except Exception as e:
                        logger.warning(f"   ⚠️ Impossible d'extraire l'artiste: {e}")

            # Fallback depuis le titre (format "Titre - Artiste")
            if not playlist_artist or playlist_artist == 'Unknown Artist':
                if ' - ' in playlist_title:
                    parts = playlist_title.split(' - ')
                    if len(parts) >= 2 and parts[0].strip().lower() != 'album':
                        playlist_artist = parts[-1].strip()

            playlist_artist = playlist_artist or 'Unknown Artist'

            songs          = []
            total_duration = 0

            for entry in info['entries']:
                if entry is None:
                    continue
                song_artist = (
                    entry.get('artist') or entry.get('creator') or
                    entry.get('uploader') or playlist_artist
                )
                if song_artist.endswith(' - Topic'):
                    song_artist = song_artist[:-8]

                song = {
                    'title':    entry.get('title', 'Unknown'),
                    'artist':   song_artist,
                    'url':      entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}",
                    'id':       entry.get('id'),
                    'duration': entry.get('duration', 0)
                }
                songs.append(song)
                total_duration += song['duration']

            logger.info(f"   ✅ {len(songs)} chansons — {playlist_title} / {playlist_artist} ({total_duration // 60}min)")

            return {
                'success':        True,
                'type':           playlist_type,
                'title':          playlist_title,
                'artist':         playlist_artist,
                'year':           playlist_year,
                'songs':          songs,
                'total_songs':    len(songs),
                'total_duration': total_duration,
                'timestamp':      datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Extraction playlist: {e}")
            return {'success': False, 'error': str(e), 'timestamp': datetime.now().isoformat()}

    # ──────────────────────────────────────────────────────────────
    # Utilitaires privés
    # ──────────────────────────────────────────────────────────────

    def _normalize_url(self, url):
        """Convertit une URL YouTube Music en URL YouTube classique."""
        if 'music.youtube.com' in url:
            match = re.search(r'[?&]v=([^&]+)', url)
            if match:
                return f'https://www.youtube.com/watch?v={match.group(1)}'
        return url

    def _clean_filename(self, name):
        """Nettoie un nom de fichier (supprime les caractères interdits)."""
        for char in '<>:"/\\|?*':
            name = name.replace(char, '')
        return name.strip()

    def _find_ffmpeg(self):
        """
        Détecte FFmpeg dans le PATH (prioritaire en environnement Docker/Linux).
        Retourne le dossier parent du binaire, ou None si introuvable.
        """
        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path:
            logger.info(f"🔧 FFmpeg détecté: {ffmpeg_path}")
            return str(Path(ffmpeg_path).parent)
        logger.warning("⚠️ FFmpeg non trouvé dans le PATH — la conversion MP3 sera impossible.")
        return None
