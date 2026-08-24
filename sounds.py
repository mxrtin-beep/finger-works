
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


def _warm_file_cache(path):
	"""Read (and discard) a file's bytes once, so the OS's file cache has
	it in memory before playback ever needs it -- see the comment above
	_play_blocking() for why. Deliberately doesn't change *how* playback
	reads the file afterward (still winsound's SND_FILENAME, on Windows)
	-- an earlier version instead switched playback itself to read from
	an in-memory copy (SND_MEMORY), which turned out to be the wrong fix:
	SND_MEMORY is pickier about exact WAV formatting than SND_FILENAME,
	and it was silently falling back to a Windows system/error sound
	instead of ours. This just warms the cache and leaves the
	known-working playback path alone."""
	try:
		with open(path, 'rb') as f:
			f.read()
	except OSError:
		pass


if sys.platform == 'win32':
	# Same reasoning as before: a file's first-ever read in this process
	# can be slower than every read after it, since the OS hasn't cached
	# it yet -- which is what was showing up as "the first key press
	# doesn't seem to make a sound". Doing this once here, at import time
	# (well before any real click/keypress, while the hand-tracking model
	# is still loading), moves that one-time cost out of the way, without
	# touching how the real plays below actually read the file.
	_warm_file_cache(_CLICK_PATH)
	_warm_file_cache(_KEY_PATH)


# Playback happens one sound at a time, from a single dedicated background
# thread, rather than firing each one off independently -- on macOS/Linux
# (a fresh `afplay`/`aplay` process per play) that's what stops two sounds
# close together in time from racing to open the same audio device, where
# the loser can fail silently instead of queuing up. On Windows a single
# process is already naturally serialized through one winsound call at a
# time, but routing everything through the same queue keeps this file's
# logic the same across all three platforms.
_sound_queue = queue.Queue()


def _play_blocking(path):
	if sys.platform == 'win32':
		import winsound
		# No SND_ASYNC -- this call is already on the dedicated background
		# thread below, so blocking it until playback finishes is exactly
		# what serializes plays through one at a time. SND_NODEFAULT is
		# what stops Windows from substituting its own system/error sound
		# if this ever *does* fail to play for some other reason -- better
		# to silently do nothing than play a sound that reads as "your
		# click didn't work" for a click that actually did.
		winsound.PlaySound(
			path, winsound.SND_FILENAME | winsound.SND_NODEFAULT,
		)
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
