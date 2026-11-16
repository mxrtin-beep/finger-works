"""Sound for Music mode: numpy-synthesized instruments played through
pygame.mixer.

Nothing here ships as audio files -- every note is computed from a formula,
so any pitch of any key is available and the repo stays tiny. Two kinds of
sound:

  * Struck/plucked notes (harp, keys): rendered once per (voice, pitch),
    cached as pygame Sounds, and fired-and-forgotten on a free mixer
    channel. Each trigger gets its own channel volume + stereo pan, so
    velocity and position cost nothing extra.
  * The theremin: a streaming oscillator thread that keeps one reserved
    mixer channel fed with tiny chunks, so its pitch and volume can glide
    continuously instead of being a bank of fixed notes.

pygame is optional for the rest of FingerWorks (see requirements.txt), so
everything here degrades to silence if it isn't importable -- the visuals
still work, the window just says so.
"""

import threading
import time

import numpy as np

from music_theory import midi_to_freq


class AudioEngine:
	"""Owns the mixer. `available` is False (with `error` explaining why)
	when pygame isn't installed or no audio device could be opened."""

	CHANNELS = 48

	def __init__(self):
		self.available = False
		self.error = None
		self.sample_rate = 44100
		self.channels = 2
		self._pg = None
		try:
			import pygame

			if not pygame.mixer.get_init():
				pygame.mixer.init()
			freq, fmt, channels = pygame.mixer.get_init()
			if fmt != -16:
				# Samples below are signed 16-bit. Anything else (rare: a
				# float mixer) needs re-initializing in the format we write.
				pygame.mixer.quit()
				pygame.mixer.init(frequency=44100, size=-16, channels=2)
				freq, fmt, channels = pygame.mixer.get_init()
			self.sample_rate = freq
			self.channels = channels
			pygame.mixer.set_num_channels(self.CHANNELS)
			# Channel 0 is the theremin's/strings' stream, channels 1-2 the chord
			# pad's two crossfading halves and channel 3 Paint's surf bed, so a
			# burst of plucked notes can never steal any of them.
			pygame.mixer.set_reserved(4)
			self._pg = pygame
			self.available = True
		except Exception as exc:    # no pygame, no device, ...
			self.error = str(exc) or exc.__class__.__name__

	def make_sound(self, mono):
		"""float array in -1..1 -> a pygame Sound in the mixer's format."""
		pcm = (np.clip(mono, -1.0, 1.0) * 32767.0).astype(np.int16)
		if self.channels >= 2:
			pcm = np.ascontiguousarray(np.stack([pcm] * self.channels, axis=1))
		return self._pg.sndarray.make_sound(pcm)

	def make_stereo_sound(self, left, right):
		"""Two float arrays (-1..1) -> a pygame Sound with a real left/right
		image (for wide, enveloping sounds like surf)."""
		pcm = np.stack([
			(np.clip(left, -1.0, 1.0) * 32767.0).astype(np.int16),
			(np.clip(right, -1.0, 1.0) * 32767.0).astype(np.int16),
		], axis=1)
		if self.channels < 2:
			pcm = pcm.mean(axis=1).astype(np.int16)
		return self._pg.sndarray.make_sound(np.ascontiguousarray(pcm))

	def play(self, sound, volume=1.0, pan=0.0):
		"""Fire `sound` on a free channel at `volume` (0..1), panned
		`pan` (-1 left .. +1 right) with a constant-power law. Returns the
		Channel (to fade it out later) or None if every channel was busy."""
		if not self.available:
			return None
		channel = sound.play()
		if channel is None:
			return None
		self.set_channel(channel, volume, pan)
		return channel

	def set_channel(self, channel, volume, pan=0.0):
		angle = (min(max(pan, -1.0), 1.0) + 1.0) * np.pi / 4.0
		left = min(volume * float(np.cos(angle)) * 1.2, 1.0)
		right = min(volume * float(np.sin(angle)) * 1.2, 1.0)
		channel.set_volume(max(left, 0.0), max(right, 0.0))

	def stop_all(self):
		if self.available:
			try:
				self._pg.mixer.stop()
			except Exception:
				pass


# --- Voices --------------------------------------------------------------------

def _fade_tail(y, sr, seconds=0.12):
	"""Taper the very end to zero so a note that hasn't fully decayed
	doesn't end in a click."""
	n = min(len(y), int(seconds * sr))
	y[-n:] *= np.linspace(1.0, 0.0, n) ** 2
	return y


def render_harp(freq, sr, duration=3.8):
	"""A plucked string: a stack of harmonics, with the upper ones dying
	faster than the fundamental (the way a real string's brightness fades
	as it rings), a few ms of attack, and a short noisy 'pluck' transient.

	Hot path -- a pluck that misses the NoteBank's warm cache renders on the
	spot, mid-gesture -- so it avoids per-harmonic trig/exp over the whole
	buffer: sin(k*theta) comes from the Chebyshev recurrence, and since
	harmonic k decays at a rate linear in k, exp(-r_k t) is just a running
	product of two precomputed exponentials. About 5x faster than the
	direct sum, same output.
	"""
	n = int(duration * sr)
	t = np.arange(n, dtype=np.float32) / np.float32(sr)
	theta = (2.0 * np.pi * freq) * t
	two_cos = 2.0 * np.cos(theta)

	# rate_k = (1 + 0.85 (k-1)) / 1.0  ->  exp(-rate_k t) = e1 * d^(k-1)
	e1 = np.exp(-t / 1.0)
	d = np.exp(-0.85 * t)

	y = np.zeros(n, dtype=np.float32)
	sin_prev, sin_cur = np.zeros(n, dtype=np.float32), np.sin(theta)      # sin(0), sin(theta)
	env = e1.copy()
	for k in range(1, 13):
		if freq * k > sr * 0.45:
			break
		y += (1.0 / k ** 1.25) * sin_cur * env
		sin_prev, sin_cur = sin_cur, two_cos * sin_cur - sin_prev          # sin((k+1) theta)
		env = env * d
	y *= np.minimum(1.0, t / 0.003)
	# Pluck transient: a few ms of lightly low-passed noise.
	rng = np.random.default_rng(int(freq * 100) % (2 ** 32))
	burst = rng.standard_normal(n).astype(np.float32) * np.exp(-t / 0.006) * 0.12
	burst = np.convolve(burst[: int(0.05 * sr)], np.ones(6) / 6, mode='same')
	y[: len(burst)] += burst
	y = _fade_tail(y, sr)
	return y / max(float(np.max(np.abs(y))), 1e-6) * 0.55


def render_keys(freq, sr, duration=5.0):
	"""An electric-piano / Rhodes-style tone from two-operator FM: the
	modulation index decays quickly, so the attack is bright and bell-like
	and it mellows into a warm sine as it rings."""
	n = int(duration * sr)
	t = np.arange(n) / sr
	index = 2.2 * np.exp(-t * 4.0) + 0.25
	body = np.sin(2 * np.pi * freq * t + index * np.sin(2 * np.pi * freq * t))
	tine = 0.22 * np.sin(2 * np.pi * freq * 7.0 * t) * np.exp(-t * 11.0)
	beat = 0.12 * np.sin(2 * np.pi * freq * 2.0 * t) * np.exp(-t * 2.2)
	y = (body + tine + beat) * np.exp(-t / 1.7)
	y *= np.minimum(1.0, t / 0.004)
	y = _fade_tail(y, sr)
	return y / max(np.max(np.abs(y)), 1e-6) * 0.55


def render_drop(freq, sr, duration=3.4):
	"""A soft, rounded droplet: no pluck transient and a gentle attack, so
	it never clicks or stings; a fundamental with a trace of upper harmonics
	and a slightly detuned partner for a watery shimmer; a long, smooth decay.
	Quiet and smooth by design -- the opposite of the harp's pluck."""
	n = int(duration * sr)
	t = np.arange(n) / sr
	y = (np.sin(2 * np.pi * freq * t)
		+ 0.16 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t / 0.5)
		+ 0.05 * np.sin(2 * np.pi * 3 * freq * t) * np.exp(-t / 0.25)
		+ 0.45 * np.sin(2 * np.pi * freq * 1.0035 * t))
	y *= (1.0 - np.exp(-t / 0.032)) * np.exp(-t / 1.15)
	y = _fade_tail(y, sr, 0.25)
	return y / max(np.max(np.abs(y)), 1e-6) * 0.5


VOICES = {'harp': render_harp, 'keys': render_keys, 'drop': render_drop}


class NoteBank:
	"""Lazily renders and caches one Sound per (voice, MIDI pitch).

	Rendering a few seconds of audio takes a handful of milliseconds --
	fine once, but not something to do mid-gesture -- so `warm()` fills the
	cache for a chord's notes in a background thread the moment the chord
	changes, and a pluck only renders on the spot if it somehow beat that.
	"""

	def __init__(self, engine):
		self.engine = engine
		self._cache = {}
		self._lock = threading.Lock()

	def get(self, voice, midi):
		key = (voice, int(midi))
		with self._lock:
			sound = self._cache.get(key)
		if sound is None:
			samples = VOICES[voice](midi_to_freq(midi), self.engine.sample_rate)
			sound = self.engine.make_sound(samples)
			with self._lock:
				self._cache[key] = sound
		return sound

	def warm(self, voice, midis):
		if not self.engine.available:
			return

		def work():
			for midi in midis:
				try:
					self.get(voice, midi)
				except Exception:
					return

		threading.Thread(target=work, daemon=True).start()


PAD_LOOP_SECONDS = 4.0


def render_pad(root_midi, quality, sr):
	"""A soft sustained chord that loops seamlessly.

	Every partial's frequency is snapped to a whole number of cycles per
	loop, so the end of the buffer lands exactly on its start and it can
	repeat forever with no click. Each note is doubled with a partner a
	quarter-hertz away (itself a whole number of cycles per loop), which
	beats slowly against it -- the gentle shimmer of a chorus -- and the
	whole thing breathes with a slow tremolo."""
	n = int(PAD_LOOP_SECONDS * sr)
	t = np.arange(n) / sr
	third = 3 if quality == 'min' else 4
	notes = [root_midi, root_midi + 12, root_midi + 12 + third, root_midi + 12 + 7]
	y = np.zeros(n)
	for i, midi in enumerate(notes):
		f = round(midi_to_freq(midi) * PAD_LOOP_SECONDS) / PAD_LOOP_SECONDS
		weight = 1.0 if i == 0 else 0.7
		for detune, share in ((0.0, 1.0), (0.25, 0.5)):
			ph = 2 * np.pi * (f + detune) * t
			y += weight * share * (np.sin(ph) + 0.22 * np.sin(2 * ph) + 0.06 * np.sin(3 * ph))
	y *= 0.88 + 0.12 * np.sin(2 * np.pi * 0.5 * t)
	return y / max(np.max(np.abs(y)), 1e-6) * 0.5


def _periodic_noise(n, sr, rng, cutoff):
	"""Low-passed, pink-ish noise that repeats exactly every `n` samples.

	It is made by shaping a random spectrum and inverting it, so it is
	periodic by construction -- the end lands on the start with no seam and
	it can loop forever."""
	spec = rng.standard_normal(n // 2 + 1) + 1j * rng.standard_normal(n // 2 + 1)
	f = np.fft.rfftfreq(n, 1.0 / sr)
	# a steep (12 dB/octave) roll-off, like water heard through distance, on a
	# gentle pink tilt
	shape = 1.0 / (1.0 + (f / cutoff) ** 2) / np.sqrt(np.maximum(f, 25.0) / 25.0)
	shape *= (f / 40.0) ** 2 / (1.0 + (f / 40.0) ** 2)      # nothing inaudible below ~40 Hz
	spec *= shape
	spec[0] = 0.0
	y = np.fft.irfft(spec, n)
	return y / max(np.max(np.abs(y)), 1e-9)


SURF_SECONDS = 12.0


def render_surf(sr, seconds=SURF_SECONDS, seed=7):
	"""A bed of surf as a seamless stereo loop: soft, low-passed noise whose
	loudness rises and falls like waves arriving (two per loop, with a slower
	drift on top), the right channel's waves a beat behind the left so it
	moves across the stereo field. Returns (left, right)."""
	n = int(seconds * sr)
	rng = np.random.default_rng(seed)
	t = np.arange(n) / n                       # loop phase 0..1
	out = []
	for shift in (0.0, 0.035):
		wave = 0.5 + 0.5 * np.sin(2 * np.pi * 2 * (t - shift) - np.pi / 2)
		env = (0.22 + 0.78 * wave ** 1.7) * (0.86 + 0.14 * np.sin(2 * np.pi * (t - shift) + 1.0))
		out.append(_periodic_noise(n, sr, rng, cutoff=750.0) * env)
	peak = max(np.max(np.abs(out[0])), np.max(np.abs(out[1])), 1e-9)
	return out[0] / peak * 0.5, out[1] / peak * 0.5


def render_whoosh(sr, seconds=2.4, seed=11):
	"""One wave washing in and out, once: soft noise that swells, brightens a
	little at its crest, and fades back to nothing (starts and ends silent).
	Stereo. Used for a burst."""
	n = int(seconds * sr)
	rng = np.random.default_rng(seed)
	t = np.arange(n) / n
	env = np.sin(np.pi * t ** 0.65) ** 2
	bright = env ** 2
	out = []
	for _ in range(2):
		lo = _periodic_noise(n, sr, rng, cutoff=500.0)
		hi = _periodic_noise(n, sr, rng, cutoff=1800.0)
		out.append((lo * (1 - bright) + hi * bright) * env)
	peak = max(np.max(np.abs(out[0])), np.max(np.abs(out[1])), 1e-9)
	return out[0] / peak * 0.5, out[1] / peak * 0.5


OCEAN_PAD_SECONDS = 8.0


def render_ocean_pad(root_midi, quality, sr):
	"""A deep, dreamy pad as a seamless stereo loop: pure sines only (no
	sharp edges), the notes of an open add9 chord, each doubled with a
	partner a hair away so it shimmers slowly, and every note breathing on
	its own slow cycle so the chord swells and ebbs like a tide. Every
	frequency and every breath is a whole number of cycles per loop, so it
	repeats without a seam. Returns (left, right)."""
	n = int(OCEAN_PAD_SECONDS * sr)
	t = np.arange(n) / sr
	third = 3 if quality == 'min' else 4
	notes = [(root_midi - 12, 0.8), (root_midi, 1.0), (root_midi + 7, 0.7),
		(root_midi + 12 + third, 0.5), (root_midi + 26, 0.35)]
	sides = []
	for side in (0, 1):
		y = np.zeros(n)
		for i, (midi, weight) in enumerate(notes):
			f = round(midi_to_freq(midi) * OCEAN_PAD_SECONDS) / OCEAN_PAD_SECONDS
			breath = 0.78 + 0.22 * np.sin(2 * np.pi * t / OCEAN_PAD_SECONDS + (i + 0.5 * side) * 1.3)
			detune = (0.125, -0.125)[side]
			ph = 2 * np.pi * f * t
			note = np.sin(ph) + 0.3 * np.sin(2 * np.pi * (f + detune) * t)
			if midi < 60:
				note = note + 0.12 * np.sin(2 * ph)        # a touch of body on the low notes
			y += weight * breath * note
		sides.append(y)
	peak = max(np.max(np.abs(sides[0])), np.max(np.abs(sides[1])), 1e-9)
	return sides[0] / peak * 0.5, sides[1] / peak * 0.5


class SurfVoice:
	"""Paint's continuous bed of surf: one looping stereo sound on its own
	reserved channel. The loop takes a moment to compute, so it is rendered
	on a background thread and starts the moment it's ready."""

	FADE_MS = 2500

	def __init__(self, engine):
		self.engine = engine
		self._sound = None
		self._channel = None
		self._want = False
		self.level = 0.0
		self._thread = None

	def start(self, level=0.0):
		if not self.engine.available:
			return
		self.level = level
		self._want = True
		if self._sound is not None:
			self._play()
		elif self._thread is None:
			self._thread = threading.Thread(target=self._prepare, daemon=True)
			self._thread.start()

	def _prepare(self):
		try:
			left, right = render_surf(self.engine.sample_rate)
			self._sound = self.engine.make_stereo_sound(left, right)
		except Exception:
			self._thread = None
			return
		self._thread = None
		if self._want:
			self._play()

	def _play(self):
		try:
			channel = self.engine._pg.mixer.Channel(3)
			channel.play(self._sound, loops=-1, fade_ms=self.FADE_MS)
			channel.set_volume(self.level, self.level)
			self._channel = channel
		except Exception:
			self._channel = None

	@property
	def wanted(self):
		return self._want

	def set_level(self, level):
		self.level = level
		if self._channel is not None and self._want:
			self._channel.set_volume(level, level)

	def stop(self):
		self._want = False
		if self._channel is not None:
			try:
				self._channel.fadeout(600)
			except Exception:
				pass
			self._channel = None


class PadVoice:
	"""The chord pad: plays under whichever instrument is active, so
	changing the chord is always *audible* -- on the keys (whose notes are
	scale notes, identical whatever the chord) as much as on the harp.

	Two reserved mixer channels alternate: on a chord change the new chord
	fades in on one while the old one fades out on the other."""

	FADE_MS = 700

	def __init__(self, engine, renderer=None):
		"""`renderer(root_midi, quality, sample_rate)` returns a mono array or
		a (left, right) pair; the default is the plain chord pad."""
		self.engine = engine
		self._renderer = renderer or render_pad
		self._cache = {}
		self._channels = [None, None]
		self._current = None
		self._side = 0

	def set_chord(self, root_pc, quality, level):
		if not self.engine.available:
			return
		key = (int(root_pc), quality)
		if key == self._current:
			return
		self._current = key
		root = 45 + ((root_pc - 45) % 12)
		sound = self._cache.get(key)
		if sound is None:
			data = self._renderer(root, quality, self.engine.sample_rate)
			if isinstance(data, tuple):
				sound = self.engine.make_stereo_sound(*data)
			else:
				sound = self.engine.make_sound(data)
			self._cache[key] = sound
		old = self._channels[self._side]
		self._side ^= 1
		channel = self.engine._pg.mixer.Channel(1 + self._side)
		channel.play(sound, loops=-1, fade_ms=self.FADE_MS)
		channel.set_volume(level, level)
		self._channels[self._side] = channel
		if old is not None:
			old.fadeout(self.FADE_MS)

	def warm(self, chords):
		"""Render `chords` (a list of (root_pc, quality)) on a background
		thread, so switching to one later is instant rather than a hitch."""
		if not self.engine.available:
			return

		def work():
			for root_pc, quality in chords:
				key = (int(root_pc), quality)
				if key in self._cache:
					continue
				try:
					data = self._renderer(45 + ((root_pc - 45) % 12), quality, self.engine.sample_rate)
					self._cache[key] = (
						self.engine.make_stereo_sound(*data) if isinstance(data, tuple) else self.engine.make_sound(data)
					)
				except Exception:
					return

		threading.Thread(target=work, daemon=True).start()

	def set_level(self, level):
		channel = self._channels[self._side]
		if channel is not None and self.engine.available:
			channel.set_volume(level, level)

	def stop(self):
		for channel in self._channels:
			if channel is not None:
				channel.fadeout(300)
		self._channels = [None, None]
		self._current = None


class ThereminVoice:
	"""A continuously-sounding oscillator you steer with `set()`.

	A worker thread renders ~23ms chunks and queues them on the reserved
	mixer channel; frequency and amplitude glide toward their targets
	inside each chunk (no zipper noise or clicks), phase is carried
	across chunks (no seams), and a slow vibrato rides on top.
	"""

	CHUNK = 1024
	GLIDE_TAU = 0.045         # seconds: how quickly pitch follows its target
	AMP_TAU = 0.05            # ...and loudness (an attack/release time)
	GAIN = 0.32

	def __init__(self, engine):
		self.engine = engine
		self.freq_target = 440.0
		self.amp_target = 0.0
		self.vibrato = 0.0
		self._freq = 440.0
		self._amp = 0.0
		self._phase = 0.0
		self._vib_phase = 0.0
		self._stop = threading.Event()
		self._thread = None

	def start(self):
		if not self.engine.available or self._thread is not None:
			return
		self._thread = threading.Thread(target=self._run, daemon=True)
		self._thread.start()

	def set(self, freq=None, amp=None, vibrato=None):
		if freq is not None:
			self.freq_target = float(freq)
		if amp is not None:
			self.amp_target = float(amp)
		if vibrato is not None:
			self.vibrato = float(vibrato)

	def stop(self):
		self._stop.set()
		if self._thread is not None:
			self._thread.join(timeout=1.0)
			self._thread = None
		if self.engine.available:
			try:
				self.engine._pg.mixer.Channel(0).stop()
			except Exception:
				pass

	def _render_chunk(self):
		sr = self.engine.sample_rate
		n = self.CHUNK
		dt = n / sr

		# Exponential glide toward the targets, interpolated across the chunk.
		f_next = self._freq + (self.freq_target - self._freq) * (1.0 - np.exp(-dt / self.GLIDE_TAU))
		a_next = self._amp + (self.amp_target - self._amp) * (1.0 - np.exp(-dt / self.AMP_TAU))
		freq = np.linspace(self._freq, f_next, n, endpoint=False)
		amp = np.linspace(self._amp, a_next, n, endpoint=False)
		self._freq, self._amp = f_next, a_next

		vib_t = self._vib_phase + np.arange(n) * (2 * np.pi * 5.5 / sr)
		self._vib_phase = (self._vib_phase + n * (2 * np.pi * 5.5 / sr)) % (2 * np.pi)
		freq = freq * (1.0 + self.vibrato * 0.014 * np.sin(vib_t))

		phase = self._phase + np.cumsum(2 * np.pi * freq / sr)
		self._phase = float(phase[-1] % (2 * np.pi))
		# A pure sine is too clinical; a little 2nd/3rd harmonic gives the
		# thin, vocal edge a real theremin has.
		return self._wave(phase) * amp * self.GAIN

	def _wave(self, phase):
		"""The timbre, as a function of phase. Overridden by BowedVoice."""
		return np.sin(phase) + 0.28 * np.sin(2 * phase) + 0.10 * np.sin(3 * phase)

	def _run(self):
		pg = self.engine._pg
		channel = pg.mixer.Channel(0)
		while not self._stop.is_set():
			try:
				if channel.get_queue() is None:
					sound = self.engine.make_sound(self._render_chunk())
					if channel.get_busy():
						channel.queue(sound)
					else:
						channel.play(sound)
				time.sleep(0.004)
			except Exception:
				time.sleep(0.05)


# Timbre of the bowed voice: (harmonic roll-off exponent, number of
# harmonics, bow-noise level). Lower exponent = brighter. One voice, in the
# middle of the violin family -- warm like a viola, still bright enough to
# sing at the top. (More entries could be added for other instruments.)
BOWED_TIMBRES = {
	'strings': (1.0, 13, 0.012),
}


class BowedVoice(ThereminVoice):
	"""A sustained bowed-string tone, steered exactly like the theremin
	(`set(freq, amp, vibrato)`; a worker thread streams chunks) but with a
	string's character: a sawtooth-like stack of harmonics whose brightness
	depends on the instrument, a faint rosin hiss that follows the bow, and a
	slower attack/release than a bare oscillator -- bows take a moment to
	set a string vibrating.
	"""

	GLIDE_TAU = 0.06
	AMP_TAU = 0.07
	GAIN = 0.5

	def __init__(self, engine, timbre='strings'):
		super().__init__(engine)
		self.set_timbre(timbre)
		self._rng = np.random.default_rng(1)

	def set_timbre(self, timbre):
		self.timbre = timbre if timbre in BOWED_TIMBRES else 'strings'
		rolloff, count, noise = BOWED_TIMBRES[self.timbre]
		self._k = np.arange(1, count + 1)
		self._weights = 1.0 / self._k ** rolloff
		self._weights /= self._weights.sum() * 0.55
		self._noise = noise

	def _wave(self, phase):
		wave = np.zeros_like(phase)
		for k, w in zip(self._k, self._weights):
			wave += w * np.sin(k * phase)
		return wave + self._noise * self._rng.standard_normal(len(phase)) * 3.0
