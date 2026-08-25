
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
	it in memory before playback ever needs it -- a file's first-ever read
	in this process can be slower than every read after it, which is what
	was showing up as "the first key press doesn't seem to make a sound".
	Doesn't change how the real plays below actually read the file."""
	try:
		with open(path, 'rb') as f:
			f.read()
	except OSError:
		pass


if sys.platform == 'win32':
	_warm_file_cache(_CLICK_PATH)
	_warm_file_cache(_KEY_PATH)


# Windows: winsound.PlaySound is called directly, synchronously (returns
# immediately -- see SND_ASYNC below), right on whatever thread calls
# play_click()/play_key(). This went through several wrong turns before
# landing back here:
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
#
# The actual fix is simpler than any of those: put SND_ASYNC back and
# stop routing Windows through the background thread at all. SND_ASYNC
# hands the sound off to the OS and returns immediately without blocking,
# which is also what makes two sounds fired close together not a problem
# on Windows in the first place -- there's no process to race, and the OS
# manages the overlap itself. SND_NODEFAULT is kept (a small genuine
# improvement over the original): if playback ever *does* fail for some
# other reason, Windows stays silent instead of substituting its own
# system/error sound, which reads as "something's wrong" for a click that
# actually worked.
def _play_windows(path):
	import winsound
	winsound.PlaySound(
		path,
		winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
	)


# macOS/Linux: still routed through a single dedicated background thread,
# one sound at a time, via subprocess.run() (which *waits* for that one
# player process to finish) rather than firing each one off independently
# -- this is what stops two sounds close together in time from racing to
# open the same audio device, where the loser can fail silently instead
# of queuing up (this is the real problem described above, genuinely
# applicable here, just never on Windows).
_sound_queue = queue.Queue()


def _play_blocking(path):
	if sys.platform == 'darwin':
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


if sys.platform != 'win32':
	# Daemon thread: never blocks program exit, even mid-playback. Not
	# started on Windows at all -- nothing there ever queues anything.
	threading.Thread(target=_sound_worker, daemon=True).start()


def _play(path):
	"""Play `path` -- immediately (Windows) or queued onto the background
	thread (macOS/Linux). A missing sound file is a silent, immediate
	no-op either way."""
	if not os.path.exists(path):
		return
	if sys.platform == 'win32':
		try:
			_play_windows(path)
		except Exception as exc:
			print(f'[WARN] Could not play sound {path}: {exc}')
	else:
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
