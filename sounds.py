
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


def _play(path):
	"""Best-effort, non-blocking, per-platform playback -- a missing sound
	file, a missing platform player, or any other hiccup here should never
	interrupt gesture control, so every failure mode is swallowed (with a
	one-line warning) rather than raised.

	No extra dependency is pulled in for this: each platform already ships
	something that can fire off a short WAV asynchronously --
	winsound (stdlib) on Windows, `afplay` on macOS, `aplay` (part of
	ALSA, near-universal on Linux) elsewhere -- so this just shells out to
	whichever applies, the same way execute_zoom() in mouse_control.py
	already does per-platform OS calls."""
	if not os.path.exists(path):
		return
	try:
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
