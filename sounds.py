
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


# --- Preferred backend: pygame.mixer --------------------------------------
#
# winsound (the fallback below) went through several rounds of real, fixed
# bugs on Windows (see _play_fallback()'s comment) and *still* plays
# intermittently unreliably even in its best-known-working configuration --
# which tracks: it's a thin wrapper around the decades-old PlaySound() WinAPI
# call, a "best-effort, simple case" API that was never Microsoft's own
# recommended choice for anything beyond a single one-off system alert, and
# has a long, well-documented history of exactly this kind of flakiness
# under rapid/repeated use. There's no further flag or calling convention to
# tune here that fixes what's an inherent limitation of the API itself.
#
# pygame.mixer talks to a real audio backend (SDL2's audio API) instead of
# wrapping PlaySound, which is a fundamentally more reliable foundation for
# this. It's optional -- if it's not installed, or its mixer can't
# initialize for any reason (no audio device, etc.), every function below
# falls back to exactly the previous behavior unchanged, so there's no
# downside to trying it. `pip install pygame` to get it; unlike simpleaudio
# (tried earlier in this project and dropped -- see git history) it's one
# of the most widely used Python packages, with mature prebuilt wheels for
# every common platform/Python version, so it's much less likely to fail
# to install the way simpleaudio did.
try:
	import pygame

	pygame.mixer.init()
	_HAVE_PYGAME = True
except Exception:
	pygame = None
	_HAVE_PYGAME = False

# pygame.mixer.Sound(path) decodes the file; doing that once per path here
# (lazily, on first use) rather than on every play() call is what makes
# repeated plays cheap.
_pygame_sounds = {}


def _play_pygame(path):
	if path not in _pygame_sounds:
		_pygame_sounds[path] = pygame.mixer.Sound(path)
	_pygame_sounds[path].play()


# --- Fallback backend: per-platform system player --------------------------

def _warm_file_cache(path):
	"""Read (and discard) a file's bytes once, so the OS's file cache has
	it in memory before playback ever needs it -- a file's first-ever read
	in this process can be slower than every read after it, which is what
	was showing up as "the first key press doesn't seem to make a sound".
	Doesn't change how the real plays below actually read the file. Only
	relevant to the winsound fallback path (pygame decodes each file once
	itself, up front, the first time it's played -- see _play_pygame())."""
	try:
		with open(path, 'rb') as f:
			f.read()
	except OSError:
		pass


if not _HAVE_PYGAME and sys.platform == 'win32':
	_warm_file_cache(_CLICK_PATH)
	_warm_file_cache(_KEY_PATH)


# Windows: winsound.PlaySound is called directly, synchronously (returns
# immediately -- see SND_ASYNC below), right on whatever thread calls
# play_click()/play_key(). This went through several wrong turns before
# landing here:
#
# - The very first version did exactly this and worked correctly.
# - A later version moved every platform's playback onto a dedicated
#   background thread with *blocking* calls (subprocess.run() on macOS/
#   Linux, winsound.PlaySound() *without* SND_ASYNC on Windows), reasoning
#   from a real macOS/Linux problem (two `afplay`/`aplay` processes
#   racing for the audio device when sounds fire close together, with the
#   loser sometimes failing silently) that never applied to Windows at
#   all -- winsound doesn't spawn a process, and needed no such fix. That
#   change broke Windows playback outright: it went completely silent.
# - Another version then tried switching Windows to SND_MEMORY instead,
#   misdiagnosing the *previous* regression as a file-caching problem --
#   SND_MEMORY turned out to be pickier about exact WAV formatting than
#   SND_FILENAME, so it silently substituted a Windows system/error sound
#   instead of ours.
# - A version after that tried checking winsound.PlaySound()'s return
#   value and retrying on a falsy result -- based on a wrong premise.
#   CPython's binding doesn't return a success/failure boolean at all: it
#   returns None on success and *raises* RuntimeError on a hard failure.
#   Since no such exception/warning was ever actually observed, the
#   underlying calls were reporting success even when the audible result
#   was wrong -- with SND_ASYNC specifically, a "successful" return only
#   means the request was handed off, not that it played correctly to
#   completion, so failures after that point are invisible to this code
#   in principle, not just in practice. That's the real reason this
#   backend is no longer the preferred one: not a flag to fix, a ceiling
#   on what winsound can guarantee. (This is also why there's no retry
#   logic here -- one would either never trigger, going by that same
#   evidence, or double up a call that already "succeeded".)
#
# SND_ASYNC hands the sound off to the OS and returns immediately without
# blocking; SND_NODEFAULT means a genuine failure stays silent instead of
# Windows substituting its own system/error sound (though, per above,
# that's not a hard guarantee across every failure path).
def _play_windows_fallback(path):
	import winsound
	winsound.PlaySound(
		path,
		winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
	)


# macOS/Linux fallback: routed through a single dedicated background
# thread, one sound at a time, via subprocess.run() (which *waits* for
# that one player process to finish) rather than firing each one off
# independently -- this is what stops two sounds close together in time
# from racing to open the same audio device, where the loser can fail
# silently instead of queuing up.
_fallback_queue = queue.Queue()


def _play_blocking_fallback(path):
	if sys.platform == 'darwin':
		subprocess.run(
			['afplay', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
		)
	else:
		subprocess.run(
			['aplay', '-q', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
		)


def _fallback_worker():
	while True:
		path = _fallback_queue.get()
		try:
			_play_blocking_fallback(path)
		except Exception as exc:
			print(f'[WARN] Could not play sound {path}: {exc}')
		finally:
			_fallback_queue.task_done()


if not _HAVE_PYGAME and sys.platform != 'win32':
	# Daemon thread: never blocks program exit, even mid-playback. Not
	# started when pygame is available, or on Windows -- neither path
	# ever queues anything onto it.
	threading.Thread(target=_fallback_worker, daemon=True).start()


def _play_fallback(path):
	if sys.platform == 'win32':
		try:
			_play_windows_fallback(path)
		except Exception as exc:
			print(f'[WARN] Could not play sound {path}: {exc}')
	else:
		_fallback_queue.put(path)


def _play(path):
	"""Play `path` via pygame if available, else the per-platform
	fallback. A missing sound file is a silent, immediate no-op either
	way."""
	if not os.path.exists(path):
		return
	if _HAVE_PYGAME:
		try:
			_play_pygame(path)
			return
		except Exception as exc:
			print(f'[WARN] pygame playback failed for {path}, falling back: {exc}')
	_play_fallback(path)


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
