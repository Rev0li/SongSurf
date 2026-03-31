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
import subprocess
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
        self.ffmpeg_bin = shutil.which('ffmpeg')

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

    def organize(self, file_path, metadata, playlist_mode=False, media_mode='mp3'):
        """
        Organise un fichier audio/vidéo téléchargé.

        Mode normal (playlist_mode=False) :
            Structure  Artist/Album/Title.mp3
            Featuring auto-détecté.

        Mode playlist (playlist_mode=True) :
            Structure  Album/Title.mp3  (dossier = nom de l'album)
            Pas de tri par artiste, chaque chanson garde ses propres tags ID3.

        Args:
            file_path (str): Chemin du fichier temporaire
            metadata (dict): {artist, album, title, year}
            playlist_mode (bool): True = mode playlist (dossier plat par album)
            media_mode (str): 'mp3' ou 'mp4'

        Returns:
            dict: {success, final_path, error}
        """
        try:
            file_path = Path(file_path)

            if not file_path.exists():
                raise FileNotFoundError(f"Fichier non trouvé: {file_path}")

            logger.info(f"📁 Organisation: {file_path.name}")

            media_mode = str(media_mode or 'mp3').lower().strip()
            extension = '.mp4' if media_mode == 'mp4' else '.mp3'

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
                final_path = dest_dir / f"{title}{extension}"

                if final_path.exists():
                    counter = 1
                    while final_path.exists():
                        final_path = dest_dir / f"{title} ({counter}){extension}"
                        counter += 1

                shutil.copy2(file_path, final_path)
                thumbnail_path = self._find_thumbnail(file_path)

                if media_mode == 'mp3':
                    self._update_tags(final_path, {
                        'artist': artist,
                        'album':  album,
                        'title':  title,
                        'year':   year,
                    }, thumbnail_path)
                    self._ensure_album_cover(dest_dir, final_path, thumbnail_path)
                else:
                    self._ensure_album_cover_from_thumbnail(dest_dir, final_path, thumbnail_path)

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
                final_path = album_dir / f"{title}{extension}"

                if final_path.exists():
                    logger.debug(f"   ⚠️ Doublon détecté, ajout d'un suffixe")
                    counter = 1
                    while final_path.exists():
                        final_path = album_dir / f"{title} ({counter}){extension}"
                        counter += 1

                shutil.copy2(file_path, final_path)
                thumbnail_path = self._find_thumbnail(file_path)

                if media_mode == 'mp3':
                    self._update_tags(final_path, {
                        'artist': artist,
                        'album':  album,
                        'title':  title,
                        'year':   year,
                    }, thumbnail_path)
                    self._ensure_album_cover(album_dir, final_path, thumbnail_path)
                else:
                    self._ensure_album_cover_from_thumbnail(album_dir, final_path, thumbnail_path)

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

    def _ensure_album_cover(self, album_dir, track_path, thumbnail_path=None, overwrite=False):
        """Crée cover.jpg dans le dossier album si absent (ou overwrite=True)."""
        try:
            album_dir = Path(album_dir)
            cover_path = album_dir / 'cover.jpg'
            if not overwrite and cover_path.exists() and cover_path.stat().st_size > 0:
                return False

            img_data = None

            # Priorité: image sidecar yt-dlp (souvent de meilleure qualité)
            if thumbnail_path and Path(thumbnail_path).exists():
                img_data, _ = self._convert_image_to_jpeg(thumbnail_path)

            # Fallback: extraire l'APIC embarqué du MP3
            if not img_data:
                apic_data = self._extract_apic_bytes(track_path)
                if apic_data:
                    img_data = self._convert_image_bytes_to_jpeg(apic_data)

            # Dernier fallback: extraction via ffmpeg (utile pour MP4 et certains flux)
            if not img_data and self._extract_cover_with_ffmpeg(track_path, cover_path):
                logger.debug(f"   🖼️ cover.jpg extrait via ffmpeg: {cover_path.relative_to(self.music_dir)}")
                return True

            if img_data:
                cover_path.write_bytes(img_data)
                logger.debug(f"   🖼️ cover.jpg créé: {cover_path.relative_to(self.music_dir)}")
                return True

        except Exception as e:
            logger.warning(f"⚠️ Erreur création cover.jpg: {e}")

        return False

    def _ensure_album_cover_from_thumbnail(self, album_dir, track_path, thumbnail_path, overwrite=False):
        """Crée cover.jpg à partir du sidecar yt-dlp, sinon fallback ffmpeg."""
        try:
            album_dir = Path(album_dir)
            cover_path = album_dir / 'cover.jpg'
            if not overwrite and cover_path.exists() and cover_path.stat().st_size > 0:
                return False

            if thumbnail_path and Path(thumbnail_path).exists():
                img_data, _ = self._convert_image_to_jpeg(Path(thumbnail_path))
                if img_data:
                    cover_path.write_bytes(img_data)
                    logger.debug(f"   🖼️ cover.jpg créé depuis thumbnail: {cover_path.relative_to(self.music_dir)}")
                    return True

            if self._extract_cover_with_ffmpeg(track_path, cover_path):
                logger.debug(f"   🖼️ cover.jpg extrait via ffmpeg: {cover_path.relative_to(self.music_dir)}")
                return True

            return False
        except Exception as e:
            logger.warning(f"⚠️ Erreur création cover sidecar: {e}")
            return False

    def _extract_cover_with_ffmpeg(self, media_path, cover_path):
        """Extrait une image cover.jpg depuis un média avec ffmpeg."""
        try:
            media_path = Path(media_path)
            cover_path = Path(cover_path)
            if not media_path.exists() or not self.ffmpeg_bin:
                return False

            cmd = [
                self.ffmpeg_bin,
                '-y',
                '-i', str(media_path),
                '-map', '0:v:0',
                '-frames:v', '1',
                '-q:v', '2',
                str(cover_path),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if proc.returncode == 0 and cover_path.exists() and cover_path.stat().st_size > 0:
                return True

            # Fallback si aucun stream vidéo détecté avec map strict
            cmd_fallback = [
                self.ffmpeg_bin,
                '-y',
                '-i', str(media_path),
                '-frames:v', '1',
                '-q:v', '2',
                str(cover_path),
            ]
            proc2 = subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=25)
            return proc2.returncode == 0 and cover_path.exists() and cover_path.stat().st_size > 0
        except Exception:
            return False

    def extract_album_covers(self, overwrite=False):
        """
        Génère cover.jpg dans chaque dossier album de la bibliothèque.

        Structure gérée:
                    - Mode normal   : Artist/Album/*.(mp3|mp4)
                    - Mode playlist : Album/*.(mp3|mp4)
        """
        scanned = 0
        created = 0
        skipped = 0

        try:
            if not self.music_dir.exists():
                return {
                    'success': False,
                    'error': f"Dossier musique introuvable: {self.music_dir}",
                    'albums_scanned': 0,
                    'covers_created': 0,
                    'covers_skipped': 0,
                }

            for subdir in self.music_dir.iterdir():
                if not subdir.is_dir():
                    continue

                direct_media = sorted(
                    [p for p in subdir.iterdir() if p.is_file() and p.suffix.lower() in ('.mp3', '.mp4')],
                    key=lambda p: p.name.lower()
                )
                subdirs = [d for d in subdir.iterdir() if d.is_dir()]

                # Mode playlist: Album/*.(mp3|mp4)
                if direct_media:
                    scanned += 1
                    if self._ensure_album_cover(subdir, direct_media[0], overwrite=overwrite):
                        created += 1
                    else:
                        skipped += 1
                    continue

                # Mode normal: Artist/Album/*.(mp3|mp4)
                for album_dir in subdirs:
                    media_files = sorted(
                        [p for p in album_dir.iterdir() if p.is_file() and p.suffix.lower() in ('.mp3', '.mp4')],
                        key=lambda p: p.name.lower()
                    )
                    if not media_files:
                        continue
                    scanned += 1
                    if self._ensure_album_cover(album_dir, media_files[0], overwrite=overwrite):
                        created += 1
                    else:
                        skipped += 1

            logger.info(
                f"🖼️ Covers extraites: {created} créées, {skipped} ignorées, {scanned} albums analysés"
            )
            return {
                'success': True,
                'albums_scanned': scanned,
                'covers_created': created,
                'covers_skipped': skipped,
                'overwrite': bool(overwrite),
                'timestamp': datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"❌ extract_album_covers: {e}")
            return {
                'success': False,
                'error': str(e),
                'albums_scanned': scanned,
                'covers_created': created,
                'covers_skipped': skipped,
                'overwrite': bool(overwrite),
                'timestamp': datetime.now().isoformat(),
            }

    def _extract_apic_bytes(self, mp3_path):
        """Retourne les bytes APIC embarqués dans un MP3, sinon None."""
        try:
            audio = MP3(mp3_path, ID3=ID3)
            if not audio.tags:
                return None
            for frame in audio.tags.values():
                if isinstance(frame, APIC) and getattr(frame, 'data', None):
                    return frame.data
        except Exception:
            return None
        return None

    def _convert_image_bytes_to_jpeg(self, image_bytes):
        """Convertit des bytes image en JPEG compatible players."""
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')

                width, height = img.size
                if width != height:
                    min_dim = min(width, height)
                    left = (width - min_dim) // 2
                    top = (height - min_dim) // 2
                    right = left + min_dim
                    bottom = top + min_dim
                    img = img.crop((left, top, right, bottom))

                max_size = 1000
                if img.width > max_size or img.height > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=90, optimize=True)
                return buffer.getvalue()
        except Exception:
            return None

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

            # AJOUTER AVANT max_size :
            # Crop en carré 1:1
            width, height = img.size
            
            if width != height:
                min_dim = min(width, height)
                left = (width - min_dim) // 2
                top = (height - min_dim) // 2
                right = left + min_dim
                bottom = top + min_dim
                img = img.crop((left, top, right, bottom))
                logger.debug(f"✂️ Image croppée: {min_dim}x{min_dim}")

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
