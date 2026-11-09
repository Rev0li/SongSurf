"""
Estimation du pourcentage d'avancement du titre en cours.
"""
import math

from core import queue

# ── Avancement estimé du titre en cours (SSF-13) ───────────────────────────────
# yt-dlp ne donne l'avancement que du téléchargement, qui va vite ; la conversion
# FFmpeg, la plus longue, n'en donne aucun : la barre restait figée sur un palier
# puis sautait. On estime donc au temps écoulé, par rapport à la durée réelle des
# titres précédents (moyennes glissantes gardées en base, donc conservées quand
# SongSurf est mis en veille). Les phases réelles servent de plancher et de plafond.
SONG_SECS_DEFAULT = 20.0   # durée de traitement d'un titre sans durée connue (s)
SONG_RATE_DEFAULT = 0.08   # s de traitement par s d'audio (3 min ≈ 15 s)
_SMOOTHING        = 0.3    # poids du dernier titre dans la moyenne glissante
_PHASE_BOUNDS = {          # phase → (plancher, plafond) en %
    'downloading': (0.0, 45.0),
    'converting':  (30.0, 92.0),
    'organizing':  (90.0, 99.0),
}
_song_clock = {'started': None, 'expected': SONG_SECS_DEFAULT}


def _timing_value(key: str, default: float) -> float:
    try:
        value = float(queue.store.meta_get(key) or default)
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def _expected_song_seconds(duration) -> float:
    """Temps de traitement attendu pour un titre de `duration` secondes d'audio."""
    try:
        duration = float(duration or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration > 0:
        return max(3.0, duration * _timing_value('song_rate', SONG_RATE_DEFAULT))
    return _timing_value('song_secs', SONG_SECS_DEFAULT)


def _learn_song_timing(elapsed: float, duration) -> None:
    """Met à jour les moyennes après un titre réellement téléchargé."""
    if elapsed <= 0:
        return
    def blend(key, default, sample):
        old = _timing_value(key, default)
        queue.store.meta_set(key, f'{old + _SMOOTHING * (sample - old):.4f}')
    blend('song_secs', SONG_SECS_DEFAULT, elapsed)
    try:
        duration = float(duration or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration > 0:
        blend('song_rate', SONG_RATE_DEFAULT, elapsed / duration)


def _song_percent(phase: str, raw_pct: float, elapsed: float, expected: float) -> float:
    """Avancement d'un titre (0-100) qui ne recule pas quand la phase change.

    Estimation au temps : 90 % à la durée attendue, puis approche lente de 99 %
    si le titre est plus long que prévu. Bornée par la phase réelle.
    """
    if phase == 'completed':
        return 100.0
    ratio = elapsed / expected if expected > 0 else 0.0
    estimate = 90.0 * ratio if ratio <= 1 else 90.0 + 9.0 * (1 - math.exp(-1.5 * (ratio - 1)))
    floor, ceiling = _PHASE_BOUNDS.get(phase, (0.0, 45.0))
    if phase == 'downloading':
        floor = max(0.0, min(100.0, raw_pct)) * 0.3   # vrai avancement du téléchargement
    return round(max(floor, min(ceiling, estimate)), 1)
