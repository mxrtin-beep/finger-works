
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


# On Windows, every sound's raw bytes are read from disk exactly once,
# here, at import time, and played from memory (winsound's SND_MEMORY)
# from then on -- not read fresh off disk on every single play (the
# previous approach, SND_FILENAME). Reading a file for the very first time
# in a process can be noticeably slower than every read after it (the OS
# hasn't cached it yet), which lines up with "the very first key press of
# a session doesn't seem to make a sound" far better than anything else
# tried so far: click.wav gets replayed constantly once any click has
# happened (so it's cache-warm almost immediately and mostly seems fine),
# while a first-ever key press was hitting key.wav's own cold, uncached
# first read every time. Reading it here at import time (well before any
# real click/keypress, while the hand-tracking model is still loading)
# moves that one-time cost out of the way entirely, for both sounds, since
# playback afterward never touches the filesystem again.
if sys.platform == 'win32':
	def _read_wav_bytes(path):
		if not os.path.exists(path):
			return None
		with open(path, 'rb') as f:
			return f.read()

	_CLICK_BYTES = _read_wav_bytes(_CLICK_PATH)
	_KEY_BYTES = _read_wav_bytes(_KEY_PATH)
else:
	_CLICK_BYTES = None
	_KEY_BYTES = None


# Playback happens one sound at a time, from a single dedicated background
# thread, rather than firing each one off independently -- on macOS/Linux
# (a fresh `afplay`/`aplay` process per play there, since winsound's
# SND_MEMORY trick above is Windows-only) that's what stops two sounds
# close together in time from racing to open the same audio device, where
# the loser can fail silently instead of queuing up. Even on Windows,
# where a single process is already naturally serialized through one
# winsound call at a time, routing everything through the same queue
# keeps the two platforms' code paths (and this file) simpler.
_sound_queue = queue.Queue()


def _play_blocking(path):
	if sys.platform == 'win32':
		import winsound
		data = _CLICK_BYTES if path == _CLICK_PATH else _KEY_BYTES
		if data is None:
			return
		# No SND_ASYNC -- this call is already on the dedicated background
		# thread below, so blocking it until playback finishes is exactly
		# what serializes plays through one at a time.
		winsound.PlaySound(data, winsound.SND_MEMORY)
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


def _play(path):
	"""Queue `path` to play on the background sound thread -- a missing
	sound file is checked for here (not on the worker thread) so it's a
	silent, immediate no-op rather than a queued failure. On Windows the
	path is just a lookup key into the preloaded bytes above (see
	_play_blocking()); the file itself isn't touched again after import."""
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
