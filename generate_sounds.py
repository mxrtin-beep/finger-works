
"""One-off script that generated sounds/click.wav and sounds/key.wav --
not imported by the running program, just checked in so the sounds are
reproducible/tweakable without needing an external audio tool. Re-run it
(`python generate_sounds.py`) after editing the parameters below to
regenerate both files.

Both are short, low-amplitude synthetic tones with a quick linear attack
and an eased-out decay (envelope**2, not a straight ramp) -- meant to be a
light, barely-there tap rather than an obvious "beep": no click/pop at the
start (the attack ramp) or abrupt cutoff at the end (the eased decay), and
low enough amplitude that they're felt more than heard, per the "light,
not intrusive or annoying" ask that started these. Click's pitch is lower
and its "feel" from a slightly longer decay is why it reads as a heavier,
outward action than the quicker/higher key tick.
"""

import math
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


if __name__ == '__main__':
	# Click: a short, soft "tap" -- low-ish pitch, ~45ms, gentle amplitude.
	write_wav('sounds/click.wav', freq=740, duration_s=0.045, amplitude=0.28, attack_s=0.003, decay_s=0.038)

	# Key: a slightly higher, even shorter "tick" so it reads as distinct
	# from the click sound without being a different kind of noise.
	write_wav('sounds/key.wav', freq=1050, duration_s=0.032, amplitude=0.22, attack_s=0.002, decay_s=0.026)

	print('Wrote sounds/click.wav and sounds/key.wav')
