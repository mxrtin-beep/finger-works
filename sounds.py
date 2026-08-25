
import os
import queue
import struct
import subprocess
import sys
import tempfile
import threading
import wave

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

# 0.0 (silent) to 1.0 (full volume, the level click.wav/key.wav were
# generated at) -- see settings.py's 'sound_volume' and set_volume() below.
_volume = 1.0

# Windows fallback only (see _play_windows_fallback below): the near-silent
# volume a key sound is still played at even while Settings -> "Keyboard
# sounds" is off, as a mitigation for the Windows system "ding" reported
# happening in exactly that state. See play_key()'s comment for the full
# reasoning/caveats -- this is a best-effort mitigation, not a confirmed fix.
_SUPPRESS_VOLUME = 0.02


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


def set_volume(volume):
	"""0.0 (silent) to 1.0 (full volume). Applied to every future
	play_click()/play_key() call -- see settings.py's 'sound_volume' and
	main_fast.py's handle_settings_changed(), which calls this whenever the
	Settings window's volume slider changes."""
	global _volume
	_volume = max(0.0, min(1.0, volume))


def get_volume():
	return _volume


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
# of the most widely used Python packages, with prebuilt wheels for every
# common platform/Python version -- *except* very new Python releases,
# where a prebuilt wheel may not exist yet (observed failing to build
# from source on Python 3.14: missing MSVC build tools/distutils, not
# worth chasing unless a full Visual Studio Build Tools setup is already
# in place). On an unsupported Python version, `pip install pygame` will
# simply fail and this whole block no-ops -- see requirements.txt.
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


def _play_pygame(path, volume):
	if path not in _pygame_sounds:
		_pygame_sounds[path] = pygame.mixer.Sound(path)
	sound = _pygame_sounds[path]
	# set_volume() takes effect on the *next* play() call, not retroactively
	# on one already playing -- fine here since play() always follows it
	# immediately below, on the same call.
	sound.set_volume(volume)
	sound.play()


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
# - A version after *that* added SND_NODEFAULT (meant to stop Windows
#   substituting its own system/error sound on a genuine failure) and,
#   later, an explicit PlaySound(None, SND_PURGE) call right before every
#   play (a known mitigation for winsound flakiness under repeated
#   calls, stopping whatever winsound is currently doing before starting
#   the new sound). Neither actually fixed the intermittent system-sound
#   substitution -- it was still happening with both in place. Both are
#   removed here, back to plain SND_FILENAME | SND_ASYNC -- exactly the
#   very first version's flags, the only configuration of this backend
#   that was never actually reported to have this problem. Worth being
#   honest about what this means: there's no remaining evidence any
#   winsound flag combination fixes this reliably on every system, so
#   this is "known to not make it worse" more than "confirmed to fix
#   it" -- pygame remains the real fix, whenever a prebuilt wheel for
#   your Python version is available.
# winsound.PlaySound has no volume parameter at all -- the only way to make
# it play quieter is to hand it audio data that's already quieter. Rather
# than rewrite each play, the scaled-down samples are written out to a
# temp WAV file once per (source file, rounded volume) combination and
# reused after that -- click.wav/key.wav only have two possible source
# paths, and the volume slider only changes occasionally, so this cache
# stays tiny in practice. Assumes 16-bit PCM, which is exactly what
# generate_sounds.py produces (see its write_wav()); anything else falls
# back to the unscaled original file rather than risk corrupting the
# audio.
_scaled_wav_cache = {}


def _scaled_wav_path(path, volume):
	if volume >= 0.999:
		return path
	bucket = round(volume, 2)
	key = (path, bucket)
	if key in _scaled_wav_cache:
		return _scaled_wav_cache[key]

	try:
		with wave.open(path, 'rb') as wf:
			params = wf.getparams()
			frames = wf.readframes(wf.getnframes())
		if params.sampwidth != 2:
			raise ValueError(f'unsupported sample width {params.sampwidth}')
		sample_count = len(frames) // 2
		samples = struct.unpack(f'<{sample_count}h', frames)
		scaled = [max(-32768, min(32767, int(s * bucket))) for s in samples]
		out_frames = struct.pack(f'<{sample_count}h', *scaled)

		fd, out_path = tempfile.mkstemp(suffix='.wav', prefix='fw_snd_')
		os.close(fd)
		with wave.open(out_path, 'wb') as wf_out:
			wf_out.setparams(params)
			wf_out.writeframes(out_frames)
	except Exception as exc:
		print(f'[WARN] Could not scale volume for {path}: {exc}')
		return path

	_scaled_wav_cache[key] = out_path
	return out_path


def _play_windows_fallback(path, volume):
	import winsound
	winsound.PlaySound(_scaled_wav_path(path, volume), winsound.SND_FILENAME | winsound.SND_ASYNC)


# macOS/Linux fallback: routed through a single dedicated background
# thread, one sound at a time, via subprocess.run() (which *waits* for
# that one player process to finish) rather than firing each one off
# independently -- this is what stops two sounds close together in time
# from racing to open the same audio device, where the loser can fail
# silently instead of queuing up.
_fallback_queue = queue.Queue()


def _play_blocking_fallback(path, volume):
	if sys.platform == 'darwin':
		# afplay's -v takes 0.0-1.0 directly, so no pre-scaling needed here
		# (unlike winsound, which has no volume argument at all -- see
		# _scaled_wav_path above).
		subprocess.run(
			['afplay', '-v', str(volume), path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
		)
	else:
		# Plain `aplay` has no per-play volume flag (it plays raw to the
		# configured ALSA/PulseAudio mixer level) -- Linux keyboard/click
		# sounds play at whatever volume is baked into the WAV file itself
		# regardless of the Settings slider until this has a real ALSA/
		# PulseAudio volume call behind it.
		subprocess.run(
			['aplay', '-q', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
		)


def _fallback_worker():
	while True:
		path, volume = _fallback_queue.get()
		try:
			_play_blocking_fallback(path, volume)
		except Exception as exc:
			print(f'[WARN] Could not play sound {path}: {exc}')
		finally:
			_fallback_queue.task_done()


if not _HAVE_PYGAME and sys.platform != 'win32':
	# Daemon thread: never blocks program exit, even mid-playback. Not
	# started when pygame is available, or on Windows -- neither path
	# ever queues anything onto it.
	threading.Thread(target=_fallback_worker, daemon=True).start()


def _play_fallback(path, volume):
	if sys.platform == 'win32':
		try:
			_play_windows_fallback(path, volume)
		except Exception as exc:
			print(f'[WARN] Could not play sound {path}: {exc}')
	else:
		_fallback_queue.put((path, volume))


def _play(path, volume):
	"""Play `path` at `volume` (0.0-1.0) via pygame if available, else the
	per-platform fallback. A missing sound file is a silent, immediate
	no-op either way."""
	if volume <= 0.0 or not os.path.exists(path):
		return
	if _HAVE_PYGAME:
		try:
			_play_pygame(path, volume)
			return
		except Exception as exc:
			print(f'[WARN] pygame playback failed for {path}, falling back: {exc}')
	_play_fallback(path, volume)


def play_click():
	"""Call on every left/right-click press (the edge-trigger moment, not
	held/dragging) -- no-op unless Settings -> "Click sounds" is on."""
	if _click_sounds_enabled:
		_play(_CLICK_PATH, _volume)


def play_key():
	"""Call on every on-screen keyboard key press -- no-op unless
	Settings -> "Keyboard sounds" is on.

	Reported issue this also addresses: with Keyboard sounds off, typing
	was producing the Windows system "ding" on every key; with Keyboard
	sounds on, the ding didn't happen at all. Nothing in this codebase
	calls winsound (or anything else that plays a sound) when keyboard
	sounds are off and this branch wasn't reached -- so that ding isn't
	coming from a call this file makes; it's most likely a genuine
	Windows-level beep from elsewhere in the real-keystroke pipeline
	(winsound.PlaySound's legacy WinMM channel is well known to silently
	"steal" a concurrent system beep on some driver setups), which just
	happens to go audibly silent whenever *any* other winsound play is
	already using that channel -- i.e. whenever our own key sound plays.
	That's consistent with "on = no ding, off = ding" without the ding
	actually being one of our own sounds.
	This isn't confirmed root-caused (a genuine WinMM-level fix would need
	to find and silence whatever's issuing the real beep, and there's no
	such call anywhere in this codebase to point to) -- but it gives a
	concrete way to test the theory and a low-risk mitigation either way:
	a key sound still plays here even with Keyboard sounds off, just
	scaled down to near-silent (_SUPPRESS_VOLUME) rather than skipped, on
	the Windows fallback path specifically (pygame goes through a real
	audio backend, not WinMM, so it was never a suspect here). If the
	ding stops happening, that confirms the theory; if it doesn't, this
	mitigation is harmless (near-silent, not audible) and should be
	reverted rather than escalated with more winsound flags -- that
	guessing game already burned several rounds on the click-sound issue
	earlier and isn't worth repeating without better evidence.
	"""
	if _keyboard_sounds_enabled:
		_play(_KEY_PATH, _volume)
	elif sys.platform == 'win32' and not _HAVE_PYGAME:
		_play(_KEY_PATH, _SUPPRESS_VOLUME)
