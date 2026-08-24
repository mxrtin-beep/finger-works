
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
association for a sound meant to confirm something worked. It's a short
filtered-noise "tap" (like a mouse or trackpad click) with a soft low thud
underneath for a bit of body, instead of a held pitched tone.
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
	path, sample_rate=44100, duration_s=0.05, noise_decay_s=0.010,
	thud_freq=190, amplitude=0.38, seed=7,
):
	"""A short, soft "tap" built from two layers rather than one tone:

	- A burst of noise, low-pass-filtered (a simple one-pole filter, not a
	  proper EQ, but enough to dull raw white noise from a harsh "hiss"
	  into a rounder "thock") and decaying very fast (noise_decay_s) --
	  this is the actual percussive "click" part.
	- A soft, low sine ("thud") decaying over the whole duration, mixed
	  in quietly underneath for a touch of body/warmth so it doesn't feel
	  like pure static.

	Neither layer holds a clear pitch long enough to read as a "beep" or
	alert tone the way the click sound's first version did.
	"""
	rnd = random.Random(seed)
	n = int(sample_rate * duration_s)
	attack_s = 0.001
	frames = []
	lp_state = 0.0
	lp_alpha = 0.35  # how much of each new noise sample bleeds through

	for i in range(n):
		t = i / sample_rate

		raw_noise = rnd.uniform(-1.0, 1.0)
		lp_state += lp_alpha * (raw_noise - lp_state)
		noise_env = max(0.0, 1.0 - t / noise_decay_s) ** 2
		noise = lp_state * noise_env

		thud_env = max(0.0, 1.0 - t / duration_s) ** 2
		thud = math.sin(2 * math.pi * thud_freq * t) * thud_env

		sample = 0.6 * noise + 0.5 * thud
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
	# per play, or simpleaudio if installed -- see sounds.py) have some
	# device/process startup latency of their own, and a clip that short
	# can finish (or get clipped) before playback has actually started, so
	# it plays as silence even though the file's samples are genuinely
	# non-zero. 60ms -- still clearly the shorter/lighter of the two
	# sounds -- gives it enough of a window to actually be heard.
	write_wav('sounds/key.wav', freq=1050, duration_s=0.06, amplitude=0.22, attack_s=0.003, decay_s=0.05)

	print('Wrote sounds/click.wav and sounds/key.wav')
