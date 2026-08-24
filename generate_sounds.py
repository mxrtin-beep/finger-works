
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

Click has been through several redesigns:

1. A held 740Hz sine (~45ms) -- sounded like a system alert/error "bonk".
2. A noise burst plus a soft low sine "thud" underneath for body -- the
   thud read as heavy/harsh no matter how quiet it was mixed.
3. Noise burst plus a brief high pop resonance, no thud -- fixed the
   harshness, but noise-based sounds have an inherent "scratchy"/staticky
   texture (like radio static) that got *more* noticeable, not less, once
   the noise had to be loud enough to actually be heard (an earlier tuning
   pass of this version was so quiet it was closer to inaudible).

Random noise was the wrong ingredient for "light click", not just wrongly
tuned -- so this version drops noise synthesis entirely. It's a single
short pure tone that *sweeps* pitch downward (freq_start -> freq_end)
rather than holding one frequency: a held tone is what read as a "beep"
in version 1, and a downward glide is closer to how a real mechanical
click/tap actually sounds (a brief resonance whose pitch relaxes as it
decays) without needing noise to feel percussive.
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


def write_click(
	path, sample_rate=44100, duration_s=0.045,
	freq_start=900, freq_end=320, amplitude=0.26, attack_s=0.001,
):
	"""A single tone that glides in pitch from freq_start down to
	freq_end over its (short) duration, instead of holding one frequency
	-- see this file's module docstring for why: a held tone read as a
	"beep", and noise (tried in between) read as harsh/scratchy static no
	matter how it was tuned. A moving pitch reads as a natural, brief
	resonance decaying -- closer to an actual click/tap -- without either
	problem.

	The envelope's decay exponent (1.4, chosen by ear/feel rather than
	anything physically modeled) front-loads the energy into roughly the
	first half of duration_s, so despite being a genuinely short sound it
	carries enough total energy (RMS) to actually be heard -- see
	write_wav()'s docstring reasoning, same idea applied here: peak sample
	level isn't what makes a sound audible, energy integrated over its
	whole duration is.
	"""
	n = int(sample_rate * duration_s)
	frames = []
	phase = 0.0

	for i in range(n):
		t = i / sample_rate
		frac = t / duration_s

		freq = freq_start + (freq_end - freq_start) * frac
		phase += 2 * math.pi * freq / sample_rate

		env = max(0.0, 1.0 - frac) ** 1.4
		if t < attack_s:
			env *= t / attack_s

		sample = amplitude * env * math.sin(phase)
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

	print('Wrote sounds/click.wav and sounds/key.wav')
