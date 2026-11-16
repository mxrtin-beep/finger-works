import unittest

import music_theory as mt


class ChordTests(unittest.TestCase):
	def test_major_key_gives_I_IV_V_vi(self):
		self.assertEqual([c['label'] for c in mt.chord_set('C', 'Major pentatonic')], ['C', 'F', 'G', 'Am'])
		self.assertEqual([c['label'] for c in mt.chord_set('G', 'Major')], ['G', 'C', 'D', 'Em'])

	def test_minor_scales_get_the_minor_progression(self):
		self.assertEqual([c['label'] for c in mt.chord_set('A', 'Natural minor')], ['Am', 'Dm', 'F', 'G'])
		self.assertEqual([c['label'] for c in mt.chord_set('A', 'Minor pentatonic')], ['Am', 'Dm', 'F', 'G'])
		self.assertEqual([c['label'] for c in mt.chord_set('A', 'Dorian')], ['Am', 'Dm', 'F', 'G'])

	def test_blues_and_lydian_are_not_misread(self):
		# Blues has both a minor 3rd and no major 3rd -> minor flavour; Lydian is major
		self.assertTrue(mt.is_minor_scale('Blues'))
		self.assertFalse(mt.is_minor_scale('Lydian'))

	def test_chord_notes_ascend_and_stay_in_the_triad(self):
		for chord in mt.chord_set('C', 'Major'):
			notes = mt.chord_notes(chord, 10)
			self.assertEqual(notes, sorted(notes))
			self.assertEqual(len(set(notes)), 10)
			triad = {(chord['root_pc'] + i) % 12 for i in ((0, 4, 7) if chord['quality'] == 'maj' else (0, 3, 7))}
			self.assertTrue({n % 12 for n in notes} <= triad)
			self.assertEqual(notes[0] % 12, chord['root_pc'])
			self.assertGreaterEqual(notes[0], 45)
			self.assertLess(notes[0], 57)

	def test_numeric_and_string_keys_agree(self):
		self.assertEqual(mt.chord_set(9, 'Natural minor'), mt.chord_set('A', 'Natural minor'))
		self.assertEqual(mt.key_index('not a note'), 0)


class ScaleTests(unittest.TestCase):
	def test_scale_notes_belong_to_the_scale(self):
		for name, intervals in mt.SCALES.items():
			for key in ('C', 'F#', 'A#'):
				root = mt.key_index(key)
				allowed = {(root + i) % 12 for i in intervals}
				notes = mt.scale_notes(key, name, 2 * len(intervals) + 1)
				self.assertTrue({n % 12 for n in notes} <= allowed, (key, name))
				self.assertEqual(notes, sorted(notes))
				self.assertEqual(notes[0] % 12, root)
				self.assertEqual(notes[-1] - notes[0], 24)      # two octaves, root to root

	def test_snap_to_scale(self):
		# C major pentatonic: C D E G A. 61 (C#) sits between C and D.
		self.assertAlmostEqual(mt.snap_to_scale(60.2, 'C', 'Major pentatonic'), 60.0)
		self.assertAlmostEqual(mt.snap_to_scale(61.8, 'C', 'Major pentatonic'), 62.0)
		self.assertAlmostEqual(mt.snap_to_scale(60.4, 'C', 'Major pentatonic', strength=0.5), 60.2)
		self.assertAlmostEqual(mt.snap_to_scale(60.4, 'C', 'Major pentatonic', strength=0.0), 60.4)
		# octave boundaries: 71.9 should snap up to the next C (72), not stick in the octave below
		self.assertAlmostEqual(mt.snap_to_scale(71.9, 'C', 'Major pentatonic'), 72.0)
		self.assertAlmostEqual(mt.snap_to_scale(59.9, 'C', 'Major pentatonic'), 60.0)

	def test_the_keys_use_every_step_of_the_scale(self):
		# pentatonic gaps would make melodies impossible on the keys: Twinkle Twinkle needs the F
		self.assertEqual(mt.diatonic_scale('Major pentatonic'), 'Major')
		self.assertEqual(mt.diatonic_scale('Minor pentatonic'), 'Natural minor')
		self.assertEqual(mt.diatonic_scale('Blues'), 'Natural minor')
		self.assertEqual(mt.diatonic_scale('Dorian'), 'Dorian')          # already seven notes: unchanged
		strings = mt.scale_notes('C', mt.diatonic_scale('Major pentatonic'), 10, lowest=60)
		self.assertEqual(strings, [60, 62, 64, 65, 67, 69, 71, 72, 74, 76])
		twinkle = [60, 60, 67, 67, 69, 69, 67, 65, 65, 64, 64, 62, 62, 60]
		self.assertTrue(set(twinkle) <= set(strings), 'every note of the tune is on a string')
		pent = mt.scale_notes('C', 'Major pentatonic', 10, lowest=60)
		self.assertNotIn(65, pent, 'the plain pentatonic really does lack the F')

	def test_frequencies(self):
		self.assertAlmostEqual(mt.midi_to_freq(69), 440.0)
		self.assertAlmostEqual(mt.midi_to_freq(60), 261.6256, places=3)
		self.assertAlmostEqual(mt.midi_to_freq(81) / mt.midi_to_freq(69), 2.0)


if __name__ == '__main__':
	unittest.main()
