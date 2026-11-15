import types
import unittest

import numpy as np

import synth
from music_theory import midi_to_freq

SR = 44100


def dominant_freq(samples, start=2000, length=SR):
	seg = samples[start:start + length] * np.hanning(length)
	spectrum = np.abs(np.fft.rfft(seg))
	return float(np.argmax(spectrum)) * SR / length


class VoiceTests(unittest.TestCase):
	def test_notes_are_in_tune(self):
		for voice in ('harp', 'keys'):
			for midi in (45, 57, 60, 72, 84, 90):
				y = synth.VOICES[voice](midi_to_freq(midi), SR)
				self.assertAlmostEqual(dominant_freq(y), midi_to_freq(midi), delta=2.0, msg=(voice, midi))

	def test_level_is_safe_and_the_tail_does_not_click(self):
		for voice, render in synth.VOICES.items():
			y = render(midi_to_freq(60), SR)
			self.assertLessEqual(float(np.max(np.abs(y))), 0.56, voice)
			self.assertGreater(float(np.max(np.abs(y))), 0.3, voice)
			self.assertLess(abs(float(y[-1])), 1e-3, f'{voice} must end at silence')
			self.assertLess(abs(float(y[0])), 0.02, f'{voice} must start at silence')

	def test_harp_pitch_is_exact_across_the_range(self):
		# The recurrence-based renderer must not drift at high pitch / late in the note
		y = synth.render_harp(midi_to_freq(93), SR)
		late = dominant_freq(y, start=SR)          # 1s in
		self.assertAlmostEqual(late, midi_to_freq(93), delta=2.0)

	def test_harp_matches_a_direct_harmonic_sum(self):
		# render_harp computes sin(k*theta) and the decays by recurrence for
		# speed; it must stay the same waveform as the plain sum it replaces.
		for midi in (48, 64, 81):
			f = midi_to_freq(midi)
			t = np.arange(int(3.8 * SR)) / SR
			ref = np.zeros_like(t)
			for k in range(1, 13):
				if f * k > SR * 0.45:
					break
				ref += (1.0 / k ** 1.25) * np.sin(2 * np.pi * k * f * t) * np.exp(-t * (1 + 0.85 * (k - 1)))
			got = synth.render_harp(f, SR)
			a, b = ref[SR // 10:SR], got[SR // 10:SR]          # skip the pluck-noise transient
			corr = float(np.corrcoef(a, b)[0, 1])
			self.assertGreater(corr, 0.999, f'midi {midi}: waveform differs from the direct sum (r={corr:.4f})')

	def test_harp_upper_harmonics_die_faster(self):
		y = synth.render_harp(220.0, SR)
		def band(start, f):
			seg = y[start:start + 8192] * np.hanning(8192)
			sp = np.abs(np.fft.rfft(seg))
			k = int(round(f * 8192 / SR))
			return float(sp[k - 2:k + 3].max())
		early_ratio = band(500, 880.0) / band(500, 220.0)
		late_ratio = band(SR, 880.0) / band(SR, 220.0)
		self.assertLess(late_ratio, early_ratio, 'brightness should fade as the string rings')


class PadTests(unittest.TestCase):
	def test_pad_loops_seamlessly(self):
		for quality in ('maj', 'min'):
			y = synth.render_pad(48, quality, SR)
			self.assertEqual(len(y), int(synth.PAD_LOOP_SECONDS * SR))
			# the step from the last sample back to the first must be no bigger than any ordinary step
			wrap = abs(float(y[0] - y[-1]))
			typical = float(np.max(np.abs(np.diff(y))))
			self.assertLessEqual(wrap, typical * 1.05, f'{quality}: audible click when the loop repeats')

	def test_major_and_minor_pads_differ_in_the_third(self):
		def energy_at(y, freq):
			spec = np.abs(np.fft.rfft(y))
			k = int(round(freq * synth.PAD_LOOP_SECONDS))
			return float(spec[k - 1:k + 2].max())
		maj, mino = synth.render_pad(48, 'maj', SR), synth.render_pad(48, 'min', SR)
		e4, eb3 = midi_to_freq(48 + 12 + 4), midi_to_freq(48 + 12 + 3)
		self.assertGreater(energy_at(maj, e4), 5 * energy_at(maj, eb3), 'major pad has a major third')
		self.assertGreater(energy_at(mino, eb3), 5 * energy_at(mino, e4), 'minor pad has a minor third')

	def test_different_chords_are_audibly_different(self):
		roots = [synth.render_pad(r, 'maj', SR) for r in (48, 53, 55)]
		for a in range(3):
			for b in range(a + 1, 3):
				self.assertLess(abs(float(np.corrcoef(roots[a], roots[b])[0, 1])), 0.5)

	def test_pad_level_is_safe(self):
		self.assertLessEqual(float(np.max(np.abs(synth.render_pad(52, 'min', SR)))), 0.51)


class ThereminTests(unittest.TestCase):
	def make(self):
		engine = types.SimpleNamespace(sample_rate=SR, available=False)
		return synth.ThereminVoice(engine)

	def test_chunks_join_without_clicks_while_gliding_and_changing_volume(self):
		v = self.make()
		v.set(freq=440.0, amp=0.8, vibrato=0.5)
		out = np.concatenate([v._render_chunk() for _ in range(40)])
		# a click would be a jump far bigger than a sine's own slope at this level
		worst = float(np.max(np.abs(np.diff(out))))
		self.assertLess(worst, 0.2, 'discontinuity at a chunk boundary')
		v.set(freq=880.0, amp=0.2)
		out2 = np.concatenate([v._render_chunk() for _ in range(40)])
		self.assertLess(float(np.max(np.abs(np.diff(out2)))), 0.2)
		self.assertLess(abs(float(out2[0]) - float(out[-1])), 0.2)

	def test_glides_to_the_target_pitch(self):
		v = self.make()
		v.set(freq=330.0, amp=0.8, vibrato=0.0)
		for _ in range(60):
			v._render_chunk()
		out = np.concatenate([v._render_chunk() for _ in range(40)])
		self.assertAlmostEqual(dominant_freq(out, 0, len(out)), 330.0, delta=8.0)

	def test_zero_amp_is_silent(self):
		v = self.make()
		v.set(freq=440.0, amp=0.0)
		for _ in range(30):
			chunk = v._render_chunk()
		self.assertLess(float(np.max(np.abs(chunk))), 1e-4)


class BowedVoiceTests(unittest.TestCase):
	def make(self, timbre):
		return synth.BowedVoice(types.SimpleNamespace(sample_rate=SR, available=False), timbre)

	def settle(self, v, freq, amp=0.8, vibrato=0.0, secs=1.0):
		v.set(freq=freq, amp=amp, vibrato=vibrato)
		for _ in range(30):
			v._render_chunk()
		return np.concatenate([v._render_chunk() for _ in range(int(secs * SR / 1024))])

	def test_pitch_is_exact_across_the_range(self):
		for freq in (130.8, 196.0, 440.0, 880.0):
			y = self.settle(self.make('strings'), freq)
			self.assertAlmostEqual(dominant_freq(y, 0, len(y)), freq, delta=2.0, msg=freq)

	def test_a_bowed_tone_has_far_more_harmonics_than_the_theremin(self):
		bowed = self.settle(self.make('strings'), 220.0)
		theremin = self.settle(synth.ThereminVoice(types.SimpleNamespace(sample_rate=SR, available=False)), 220.0)
		def high_share(y):
			spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
			return float(spec[int(1500 * len(y) / SR):].sum() / spec.sum())
		self.assertGreater(high_share(bowed), 10 * max(high_share(theremin), 1e-4))

	def test_level_is_safe_and_audible(self):
		for freq in (110.0, 440.0):
			y = self.settle(self.make('strings'), freq, amp=1.0)
			self.assertLess(float(np.max(np.abs(y))), 0.95, freq)
			self.assertGreater(float(np.sqrt((y ** 2).mean())), 0.05, freq)

	def test_silent_when_the_bow_is_still(self):
		v = self.make('strings')
		y = self.settle(v, 110.0, amp=0.0, secs=0.5)
		self.assertLess(float(np.max(np.abs(y))), 0.02)

	def test_chunks_join_cleanly_through_a_pitch_slide_and_vibrato(self):
		v = self.make('strings')
		v.set(freq=330.0, amp=0.8, vibrato=0.5)
		a = np.concatenate([v._render_chunk() for _ in range(30)])
		v.set(freq=440.0)
		b = np.concatenate([v._render_chunk() for _ in range(30)])
		out = np.concatenate([a, b])
		# rosin hiss makes single samples jumpy, so look at a smoothed signal for seams
		smooth = np.convolve(out, np.ones(8) / 8, mode='valid')
		self.assertLess(float(np.max(np.abs(np.diff(smooth)))), 0.3)

	def test_an_unknown_timbre_falls_back_to_strings(self):
		self.assertEqual(self.make('theorbo').timbre, 'strings')

	def test_a_bow_takes_a_moment_to_speak(self):
		bow, theremin = self.make('strings'), synth.ThereminVoice(types.SimpleNamespace(sample_rate=SR, available=False))
		self.assertGreater(bow.AMP_TAU, theremin.AMP_TAU)


class EngineTests(unittest.TestCase):
	def test_engine_never_raises_without_audio(self):
		# With no usable audio device AudioEngine must degrade to available=False
		# (the visuals still work); it must never throw from its constructor.
		engine = synth.AudioEngine()
		self.assertIsInstance(engine.available, bool)
		if not engine.available:
			self.assertTrue(engine.error)
			self.assertIsNone(engine.play(None))


if __name__ == '__main__':
	unittest.main()
