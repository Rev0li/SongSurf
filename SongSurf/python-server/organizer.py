#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
organizer.py - Organisation des fichiers MP3

FONCTIONNALITÉ:
  - Organise les MP3 en structure Artist/Album/Title.mp3
  - Met à jour les tags ID3
  - Gère les doublons
"""

from pathlib import Path
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, APIC
import shutil
from datetime import datetime
import mimetypes
from PIL import Image
import io
import logging

logger = logging.getLogger('songsurf')


class MusicOrganizer:
    """Organisateur de fichiers musicaux"""

    def __init__(self, music_dir):
        self.music_dir = Path(music_dir)
        self.music_dir.mkdir(exist_ok=True, parents=True)

    def detect_featuring(self, title, artist):
        """
        Detect featuring artists in title and return cleaned data

        Returns:
            dict: {
                'main_artist': str,
                'feat_artists': list,
                'clean_title': str,
                'has_feat': bool
            }
        """
        import re

        # Patterns to detect featuring
        feat_patterns = [
            r'\(feat\.?\s+([^)]+)\)',
            r'\(ft\.?\s+([^)]+)\)',
            r'\(featuring\s+([^)]+)\)',
            r'\[feat\.?\s+([^\]]+)\]',
            r'\[ft\.?\s+([^\]]+)\]',
            r'feat\.?\s+([^-\(\[]+)',
            r'ft\.?\s+([^-\(\[]+)',
        ]

        feat_artists = []
        clean_title = title

        # Check title for featuring
        for pattern in feat_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                feat_artist = match.group(1).strip()
                feat_list = re.split(r'\s*(?:&|and|,)\s*', feat_artist)
                feat_artists.extend([a.strip() for a in feat_list if a.strip()])
                clean_title = re.sub(pattern, '', clean_title, flags=re.IGNORECASE).strip()

        # Check artist field for multiple artists
        if ' & ' in artist or ' and ' in artist or ', ' in artist or ' et ' in artist:
            artist_list = re.split(r'\s*(?:&|and|et|,)\s*', artist, flags=re.IGNORECASE)
            main_artist = artist_list[0].strip()
            feat_artists.extend([a.strip() for a in artist_list[1:] if a.strip()])
            logger.debug(f"Multiple artists: {artist} → main={main_artist}, feat={artist_list[1:]}")
        else:
            main_artist = artist

        return {
            'main_artist': main_artist,
            'feat_artists': list(set(feat_artists)),
            'clean_title': clean_title,
            'has_feat': len(feat_artists) > 0
        }

    def organize(self, file_path, metadata, playlist_mode=False):
        """
        Organise un fichier MP3.

        Mode normal (playlist_mode=False) :
            Structure  Artist/Album/Title.mp3
            Featuring auto-détecté.

        Mode playlist (playlist_mode=True) :
            Structure  Album/Title.mp3  (dossier = nom de l'album)
            Pas de tri par artiste, chaque chanson garde ses propres tags ID3.

        Args:
            file_path (str): Chemin du fichier MP3 temporaire
            metadata (dict): {artist, album, title, year}
            playlist_mode (bool): True = mode playlist (dossier plat par album)

        Returns:
            dict: {success, final_path, error}
        """
        try:
            file_path = Path(file_path)

            if not file_path.exists():
                raise FileNotFoundError(f"Fichier non trouvé: {file_path}")

            logger.info(f"📁 Organisation: {file_path.name}")

            raw_artist = metadata.get('artist', 'Unknown Artist')
            album      = metadata.get('album',  'Unknown Album')
            raw_title  = metadata.get('title',  'Unknown Title')
            year       = metadata.get('year',   '')

            thumbnail_path = None

            if playlist_mode:
                # ── MODE PLAYLIST : Album/Title.mp3 ──────────────────────
                artist = self._clean_filename(raw_artist)
                album  = self._clean_filename(album)
                title  = self._clean_filename(raw_title)

                logger.info(f"   🎵 Mode Playlist — dossier: {album} / titre: {title}")

                dest_dir = self.music_dir / album
                dest_dir.mkdir(parents=True, exist_ok=True)
                final_path = dest_dir / f"{title}.mp3"

                if final_path.exists():
                    counter = 1
                    while final_path.exists():
                        final_path = dest_dir / f"{title} ({counter}).mp3"
                        counter += 1

                shutil.copy2(file_path, final_path)
                thumbnail_path = self._find_thumbnail(file_path)

                self._update_tags(final_path, {
                    'artist': artist,
                    'album':  album,
                    'title':  title,
                    'year':   year,
                }, thumbnail_path)

            else:
                # ── MODE NORMAL : Artist/Album/Title.mp3 ─────────────────
                feat_info = self.detect_featuring(raw_title, raw_artist)
                artist = feat_info['main_artist']
                title  = feat_info['clean_title']

                if feat_info['has_feat']:
                    feat_str = ', '.join(feat_info['feat_artists'])
                    title = f"{title} (feat. {feat_str})"
                    logger.info(f"   🎭 Featuring détecté: {feat_str} → artiste principal: {artist}")

                artist = self._clean_filename(artist)
                album  = self._clean_filename(album)
                title  = self._clean_filename(title)

                logger.info(f"   🎤 {artist} / 💿 {album} / 🎵 {title} ({year})")

                album_dir = self.music_dir / artist / album
                album_dir.mkdir(parents=True, exist_ok=True)
                final_path = album_dir / f"{title}.mp3"

                if final_path.exists():
                    logger.debug(f"   ⚠️ Doublon détecté, ajout d'un suffixe")
                    counter = 1
                    while final_path.exists():
                        final_path = album_dir / f"{title} ({counter}).mp3"
                        counter += 1

                shutil.copy2(file_path, final_path)
                thumbnail_path = self._find_thumbnail(file_path)

                self._update_tags(final_path, {
                    'artist': artist,
                    'album':  album,
                    'title':  title,
                    'year':   year,
                }, thumbnail_path)

            # ── Nettoyage commun ──────────────────────────────────────────
            file_path.unlink()
            if thumbnail_path and thumbnail_path.exists():
                thumbnail_path.unlink()

            logger.info(f"   ✅ Organisé → {final_path.relative_to(self.music_dir)}")

            return {
                'success':    True,
                'final_path': str(final_path.relative_to(self.music_dir)),
                'timestamp':  datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Erreur organisation: {e}")
            return {
                'success':   False,
                'error':     str(e),
                'timestamp': datetime.now().isoformat()
            }

    def _clean_filename(self, name):
        """Nettoie un nom de fichier (supprime les caractères interdits)"""
        forbidden = '<>:"/\\|?*'
        for char in forbidden:
            name = name.replace(char, '')
        return name.strip()

    def _find_thumbnail(self, mp3_path):
        """Cherche la pochette téléchargée par yt-dlp"""
        mp3_path = Path(mp3_path)
        base_name = mp3_path.stem
        for ext in ('.jpg', '.jpeg', '.png', '.webp'):
            thumbnail = mp3_path.parent / f"{base_name}{ext}"
            if thumbnail.exists():
                logger.debug(f"   🖼️ Pochette trouvée: {thumbnail.name}")
                return thumbnail
        return None

    def _update_tags(self, file_path, metadata, thumbnail_path=None):
        """Met à jour les tags ID3 d'un fichier MP3 avec pochette"""
        try:
            audio = MP3(file_path, ID3=ID3)
            try:
                audio.add_tags()
            except Exception:
                pass

            audio.tags['TIT2'] = TIT2(encoding=3, text=metadata.get('title', ''))
            audio.tags['TPE1'] = TPE1(encoding=3, text=metadata.get('artist', ''))
            audio.tags['TALB'] = TALB(encoding=3, text=metadata.get('album', ''))

            if metadata.get('year'):
                audio.tags['TDRC'] = TDRC(encoding=3, text=metadata.get('year', ''))

            if thumbnail_path and thumbnail_path.exists():
                img_data, mime_type = self._convert_image_to_jpeg(thumbnail_path)
                if img_data:
                    audio.tags.delall('APIC')
                    audio.tags.add(APIC(
                        encoding=3,
                        mime=mime_type,
                        type=3,
                        desc='Cover',
                        data=img_data
                    ))
                    logger.debug(f"   🖼️ Pochette intégrée ({len(img_data)} bytes, {mime_type})")

            audio.save()
            logger.debug(f"   🏷️ Tags ID3 mis à jour")

        except Exception as e:
            logger.warning(f"⚠️ Erreur tags ID3: {e}")

    def _convert_image_to_jpeg(self, image_path):
        """Convertit une image en JPEG pour compatibilité maximale"""
        try:
            img = Image.open(image_path)
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            max_size = 1000
            if img.width > max_size or img.height > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=90, optimize=True)
            return buffer.getvalue(), 'image/jpeg'

        except Exception as e:
            logger.warning(f"⚠️ Erreur conversion image: {e}")
            try:
                with open(image_path, 'rb') as f:
                    img_data = f.read()
                mime_type = mimetypes.guess_type(str(image_path))[0] or 'image/jpeg'
                return img_data, mime_type
            except Exception:
                return None, None

    def get_stats(self):
        """
        Retourne les statistiques de la bibliothèque musicale.

        Gère deux structures coexistantes dans MUSIC_DIR :
          - Mode normal    : Artist/Album/Title.mp3  (3 niveaux)
          - Mode playlist  : Album/Title.mp3          (2 niveaux — dossier contient des MP3 directement)
        """
        try:
            total_artists   = 0
            total_albums    = 0
            total_playlists = 0
            total_songs     = 0
            total_duration  = 0

            for subdir in self.music_dir.iterdir():
                if not subdir.is_dir():
                    continue

                direct_mp3s = list(subdir.glob('*.mp3'))
                subdirs     = [d for d in subdir.iterdir() if d.is_dir()]

                if direct_mp3s:
                    # ── Mode Playlist : Album/Title.mp3 ──────────────────
                    total_playlists += 1
                    total_songs     += len(direct_mp3s)
                    for song in direct_mp3s:
                        try:
                            total_duration += MP3(song).info.length
                        except Exception:
                            pass
                else:
                    # ── Mode Normal : Artist/Album/Title.mp3 ─────────────
                    total_artists += 1
                    for album_dir in subdirs:
                        total_albums += 1
                        songs = list(album_dir.glob('*.mp3'))
                        total_songs += len(songs)
                        for song in songs:
                            try:
                                total_duration += MP3(song).info.length
                            except Exception:
                                pass

            hours   = int(total_duration // 3600)
            minutes = int((total_duration % 3600) // 60)

            return {
                'artists':   total_artists,
                'albums':    total_albums,
                'playlists': total_playlists,
                'songs':     total_songs,
                'total_duration_seconds':   int(total_duration),
                'total_duration_formatted': f"{hours}h {minutes}min" if hours > 0 else f"{minutes}min"
            }
        except Exception as e:
            logger.error(f"❌ get_stats: {e}")
            return {
                'artists': 0, 'albums': 0, 'playlists': 0, 'songs': 0,
                'total_duration_seconds': 0,
                'total_duration_formatted': '0min',
                'error': str(e)
            }
