
import os
import queue
import subprocess
import sys
import threading

# Two short, soft WAV files (sounds/click.wav, sounds/key.wav) -- see
# generate_sounds.py for how they were made and why they're shaped the way
# they are (quick attack, eased-out decay, low amplitude: meant to be
# felt more than heard, not an obvious "beep"). Both default off (see
# settings.py) -- enable from Settings -> "Click sounds" / "Keyboard
# sounds".
_SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sounds')
_CLICK_PATH = os.path.join(_SOUNDS_DIR, 'click.wav')
_KEY_PATH = os.path.join(_SOUNDS_DIR, 'key.wav')
_WARMUP_PATH = os.path.join(_SOUNDS_DIR, '_warmup.wav')

_click_sounds_enabled = False
_keyboard_sounds_enabled = False


def set_click_sounds_enabled(enabled):
	global _click_sounds_enabled
	_click_sounds_enabled = enabled


def set_keyboard_sounds_enabled(enabled):
	global _keyboard_sounds_enabled
	_keyboard_sounds_enabled = enabled


def get_click_sounds_enabled():
	return _click_sounds_enabled


def get_keyboard_sounds_enabled():
	return _keyboard_sounds_enabled


# Playback is a system player process per sound (winsound/afplay/aplay --
# no extra dependency needed, every platform already ships one of these).
# An earlier version tried simpleaudio instead (proper audio-API mixing,
# no per-play process spawn) specifically to dodge the problem this module
# now solves a different way -- but simpleaudio is a C extension that
# needs to compile on install, and it failed to build in practice (no
# prebuilt wheel for some platform/Python combos, and it's a fairly
# unmaintained package), so it's not a dependency here anymore.
#
# The actual problem simpleaudio was meant to fix: firing a brand new
# player process per sound means two sounds close together in time (e.g.
# switching keys quickly) can end up as two processes racing to open the
# same audio device -- and the loser of that race can fail silently
# (stderr suppressed) rather than queue up, especially on Linux's ALSA
# (`aplay`). The fix here doesn't need a new dependency: every sound is
# queued and played one at a time from a single dedicated background
# thread, using subprocess.run() (which *waits* for that one player to
# finish) instead of Popen-and-forget. That serializes every play through
# one process at a time, so there's never a second one to race against --
# and since these sounds are only 25-60ms long, queuing rather than
# overlapping is inaudible even when keys are pressed quickly.
_sound_queue = queue.Queue()


def _play_blocking(path):
	if sys.platform == 'win32':
		import winsound
		# No SND_ASYNC here (unlike the old approach) -- this call is
		# already on the dedicated background thread below, so blocking
		# it until playback finishes is exactly what serializes plays
		# through one at a time, the same as subprocess.run() does for
		# the other two platforms.
		winsound.PlaySound(path, winsound.SND_FILENAME)
	elif sys.platform == 'darwin':
		subprocess.run(
			['afplay', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
		)
	else:
		subprocess.run(
			['aplay', '-q', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
		)


def _sound_worker():
	while True:
		path = _sound_queue.get()
		try:
			_play_blocking(path)
		except Exception as exc:
			print(f'[WARN] Could not play sound {path}: {exc}')
		finally:
			_sound_queue.task_done()


# Daemon thread: never blocks program exit, even mid-playback.
threading.Thread(target=_sound_worker, daemon=True).start()

# Queued once at import time, ahead of and regardless of either sound
# setting or _play()'s file-exists check being reached from a real click/
# keypress -- the point is to get the platform sound player's *first ever*
# launch this run (which can be slower than later launches -- see
# generate_sounds.py's comment on _warmup.wav) out of the way during
# startup, while the hand-tracking model is still loading, rather than
# have it show up as your first real click or keypress not seeming to
# make a sound.
if os.path.exists(_WARMUP_PATH):
	_sound_queue.put(_WARMUP_PATH)


def _play(path):
	"""Queue `path` to play on the background sound thread -- a missing
	sound file is checked for here (not on the worker thread) so it's a
	silent, immediate no-op rather than a queued failure."""
	if not os.path.exists(path):
		return
	_sound_queue.put(path)


def play_click():
	"""Call on every left/right-click press (the edge-trigger moment, not
	held/dragging) -- no-op unless Settings -> "Click sounds" is on."""
	if _click_sounds_enabled:
		_play(_CLICK_PATH)


def play_key():
	"""Call on every on-screen keyboard key press -- no-op unless
	Settings -> "Keyboard sounds" is on."""
	if _keyboard_sounds_enabled:
		_play(_KEY_PATH)
