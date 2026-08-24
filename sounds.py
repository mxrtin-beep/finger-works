
import os
import subprocess
import sys

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


# Preferred playback path: simpleaudio, which plays through the platform's
# actual audio API (mixing overlapping sounds properly) rather than
# spawning a whole new OS process per play. That per-process approach
# (still kept below as a fallback) is what caused keyboard sounds to
# regularly go missing on fast typing: firing a new `afplay`/`aplay`
# process for every keystroke means back-to-back keys can end up with two
# processes racing to open the same audio device at once, and on `aplay`
# (ALSA) specifically the loser of that race fails to open the device at
# all -- silently, since stderr is suppressed. simpleaudio's mixing avoids
# that entirely. Typed letters didn't share this problem because each
# press already goes through a full pinch-release-repinch cycle, which is
# almost always slower than the window where two afplay/aplay launches
# actually overlap.
try:
	import simpleaudio
	_HAVE_SIMPLEAUDIO = True
except ImportError:
	simpleaudio = None
	_HAVE_SIMPLEAUDIO = False

# WaveObjects are cached per path (decoded once, not once per play) since
# simpleaudio.WaveObject.from_wave_file() reads and parses the whole file
# each time it's called -- this is instead done at most once, and then
# reused for every future play_click()/play_key() call.
_wave_object_cache = {}


def _play_via_simpleaudio(path):
	if path not in _wave_object_cache:
		_wave_object_cache[path] = simpleaudio.WaveObject.from_wave_file(path)
	_wave_object_cache[path].play()


def _play_via_subprocess(path):
	"""Fallback used only when simpleaudio isn't installed. Spawns a new
	OS process per play -- see the _HAVE_SIMPLEAUDIO comment above for why
	that's the less reliable option under rapid repeated triggers."""
	if sys.platform == 'win32':
		import winsound
		winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
	elif sys.platform == 'darwin':
		subprocess.Popen(
			['afplay', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
		)
	else:
		subprocess.Popen(
			['aplay', '-q', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
		)


def _play(path):
	"""Best-effort, non-blocking playback -- a missing sound file, missing
	player/library, or any other hiccup here should never interrupt
	gesture control, so every failure mode is swallowed (with a one-line
	warning) rather than raised."""
	if not os.path.exists(path):
		return
	try:
		if _HAVE_SIMPLEAUDIO:
			_play_via_simpleaudio(path)
		else:
			_play_via_subprocess(path)
	except Exception as exc:
		print(f'[WARN] Could not play sound {path}: {exc}')


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
