
"""One-off script that generated sounds/click.wav and sounds/key.wav --
not imported by the running program, just checked in so the sounds are
reproducible/tweakable without needing an external audio tool. Re-run it
(`python generate_sounds.py`) after editing the parameters below to
regenerate both files.

Key is a short, low-amplitude pure tone with a quick linear attack and an
eased-out decay (envelope**2, not a straight ramp) -- meant to be a light,
barely-there tick rather than an obvious "beep": no click/pop at the start
(the attack ramp) or abrupt cutoff at the end (the eased decay), and low
enough amplitude that it's felt more than heard, per the "light, not
intrusive or annoying" ask that started these.

Click is deliberately *not* a pure tone -- an early version (a 740Hz sine,
~45ms) sounded too much like a system alert/error "bonk" (the kind of
sound macOS/other OSes make for an invalid keypress), which is a bad
association for a sound meant to confirm something worked. A second
version added a soft low sine "thud" under a noise burst for a bit of
body, but that thud came out sounding heavy/harsh in practice too --
turns out any held low-frequency layer reads as a "thump", whatever its
volume. It's now just the noise burst itself (brighter/crisper than
before, since there's no longer a thud to soften against) plus a very
brief, very quiet high-pitched resonance under it for a touch of "pop"
character -- like an actual mouse/trackpad click, not a knock on wood.
"""

import math
import random
import struct
import wave


def write_wav(path, freq, duration_s, amplitude, sample_rate=44100, attack_s=0.004, decay_s=None):
	n = int(sample_rate * duration_s)
	decay_s = decay_s or duration_s
	frames = []
	for i in range(n):
		t = i / sample_rate
		if t < attack_s:
			env = t / attack_s
		else:
			env = max(0.0, 1.0 - (t - attack_s) / decay_s)
			env = env ** 2
		sample = amplitude * env * math.sin(2 * math.pi * freq * t)
		frames.append(struct.pack('<h', int(sample * 32767)))

	with wave.open(path, 'w') as f:
		f.setnchannels(1)
		f.setsampwidth(2)
		f.setframerate(sample_rate)
		f.writeframes(b''.join(frames))


def write_click(
	path, sample_rate=44100, duration_s=0.045, noise_decay_s=0.013,
	pop_freq=1500, pop_decay_s=0.006, amplitude=0.42, seed=7,
):
	"""A short "pop" built from two layers, neither of them a held tone:

	- A burst of noise, gently low-pass-filtered (a simple one-pole
	  filter, not a proper EQ, just enough to take the raw edge off white
	  noise) and decaying fast (noise_decay_s) -- the actual click/pop
	  itself.
	- A very brief, quiet, high-pitched resonance (pop_freq, decaying even
	  faster than the noise -- pop_decay_s) mixed in for a touch of "pop"
	  character, the way a real click/pop has a faint pitched ring to it
	  that pure static doesn't. This replaces an earlier version's held
	  low-frequency "thud" layer, which read as heavy/harsh no matter how
	  quiet it was mixed -- any *held*, low-pitched layer apparently reads
	  as a thump regardless of level, where a brief, high, fast-decaying
	  one doesn't.

	Kept safely away from the too-short-to-render range that key.wav ran
	into (see the comment where it's generated below) despite being
	perceptually snappier now: duration_s is still ~45ms, only the
	*audible/energetic* part of it (the first ~15ms or so) is short.
	"""
	rnd = random.Random(seed)
	n = int(sample_rate * duration_s)
	attack_s = 0.001
	frames = []
	lp_state = 0.0
	lp_alpha = 0.55  # brighter/crisper than a duller "thock" -- this is
	                 # the actual click/pop character now that there's no
	                 # thud layer underneath it to clash with

	for i in range(n):
		t = i / sample_rate

		raw_noise = rnd.uniform(-1.0, 1.0)
		lp_state += lp_alpha * (raw_noise - lp_state)
		noise_env = max(0.0, 1.0 - t / noise_decay_s) ** 2
		noise = lp_state * noise_env

		pop_env = max(0.0, 1.0 - t / pop_decay_s) ** 3
		pop = math.sin(2 * math.pi * pop_freq * t) * pop_env

		sample = 0.78 * noise + 0.16 * pop
		sample = max(-1.0, min(1.0, sample)) * amplitude
		if t < attack_s:
			sample *= t / attack_s

		frames.append(struct.pack('<h', int(sample * 32767)))

	with wave.open(path, 'w') as f:
		f.setnchannels(1)
		f.setsampwidth(2)
		f.setframerate(sample_rate)
		f.writeframes(b''.join(frames))


if __name__ == '__main__':
	write_click('sounds/click.wav')

	# Key: a light tone-based tick, distinct in *character* from click's
	# noise-based tap (not just pitch), so the two are easy to tell apart
	# by ear. Originally 32ms, which turned out to be too short to
	# reliably render at all -- most playback paths here (a fresh process
	# per play) have some device/process startup latency of their own,
	# and a clip that short can finish (or get clipped) before playback
	# has actually started, so it plays as silence even though the file's
	# samples are genuinely non-zero. 60ms -- still clearly the
	# shorter/lighter of the two sounds -- gives it enough of a window to
	# actually be heard.
	write_wav('sounds/key.wav', freq=1050, duration_s=0.06, amplitude=0.22, attack_s=0.003, decay_s=0.05)

	# Near-silent (amplitude 0.002 -- inaudible) primer clip, played once
	# automatically at startup by sounds.py regardless of whether either
	# sound setting is on. Its only purpose is to make the *first* ever
	# call to the platform sound player (afplay/aplay/winsound) happen
	# during startup instead of on your first real click/keypress -- a
	# process's first launch in a session can be slower than later ones
	# (e.g. paging in its binary/libraries from disk the first time,
	# faster from OS cache after), which lines up with "the very first
	# sound doesn't play" reports better than anything already accounted
	# for by key.wav/click.wav's own durations.
	write_wav('sounds/_warmup.wav', freq=440, duration_s=0.02, amplitude=0.002, attack_s=0.002, decay_s=0.015)

	print('Wrote sounds/click.wav, sounds/key.wav, and sounds/_warmup.wav')
