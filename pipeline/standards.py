"""Delivery standards that hold for every video, in every niche.

These are the numbers that do not depend on subject, style or channel. They
are the floor: a video can be brilliant and still fail here, and a video that
fails here is worse than it needs to be for reasons nobody will articulate —
it just sounds quiet, or the text sits under the progress bar.

Each constant carries its reason, because a number without one gets "tuned"
later by someone who does not know why it was chosen.
"""
from __future__ import annotations

# --- Audio ------------------------------------------------------------------
# YouTube normalises playback loudness to roughly -14 LUFS integrated. It turns
# DOWN anything louder and leaves quieter content alone — it never boosts. So a
# master at -21 LUFS plays about 7 dB weaker than everything around it, which
# the viewer experiences as "thin" without knowing why.
TARGET_LUFS = -14.0
# True-peak ceiling. Headroom below 0 dBFS so lossy re-encoding (which can
# overshoot the original sample peaks) does not clip.
TARGET_TRUE_PEAK_DB = -1.0
# Loudness range. Narration wants less variation than music; 11 LU is the
# common broadcast default and sits fine for speech over a bed.
TARGET_LRA = 11.0
# How far off target a finished master may be before preflight complains.
LUFS_TOLERANCE = 1.5

# --- Frame geometry ---------------------------------------------------------
# Title-safe is 80% of the frame: a 10% margin on every edge. Anything outside
# it risks being cropped by a player or a device that overscans.
TITLE_SAFE_MARGIN = 0.10
# Action-safe is more permissive; graphics may reach it, text should not.
ACTION_SAFE_MARGIN = 0.05
# The YouTube player's own chrome — progress bar, timestamp, controls — is
# drawn over the bottom of the frame. Nothing readable belongs here.
PLAYER_UI_BOTTOM = 0.08
# Captions sit above the player chrome with a margin of their own, so a
# hovering viewer never has the progress bar land on the words.
CAPTION_BOTTOM_MARGIN = 0.12

# --- Pacing -----------------------------------------------------------------
# A single unchanging frame loses attention in any niche. This is the longest
# one beat may hold without the visual changing. Generous on purpose: calm
# formats legitimately sit still far longer than explainers.
MAX_STATIC_SECONDS = 45.0
# The opening is where retention is won or lost regardless of subject. A hook
# beat that runs long is almost always throat-clearing.
MAX_HOOK_SECONDS = 20.0
# Below this, a beat is usually a fragment that should be merged with its
# neighbour — it produces a visual cut with no time to register.
MIN_BEAT_SECONDS = 1.5

# --- Metadata ---------------------------------------------------------------
TITLE_MAX_CHARS = 100          # hard YouTube limit
TITLE_IDEAL_CHARS = 60         # beyond this, mobile search results truncate
DESCRIPTION_MAX_CHARS = 5000   # hard YouTube limit
TAGS_MAX_TOTAL_CHARS = 500     # hard YouTube limit across all tags

# --- Thumbnail --------------------------------------------------------------
THUMBNAIL_MIN_WIDTH = 1280
THUMBNAIL_MIN_HEIGHT = 720
THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024
# Thumbnails are judged at roughly 210px wide in a feed. Text that cannot
# survive that reduction is decoration, not communication.
THUMBNAIL_FEED_WIDTH = 210


def safe_box(width: int, height: int, margin: float = TITLE_SAFE_MARGIN) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) of the safe rectangle, in pixels."""
    mx, my = int(width * margin), int(height * margin)
    return mx, my, width - mx, height - my


def player_ui_top(height: int) -> int:
    """The y above which content is clear of the player's own chrome."""
    return int(height * (1.0 - PLAYER_UI_BOTTOM))
