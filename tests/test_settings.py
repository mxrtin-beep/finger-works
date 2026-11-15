import json
import os
import tempfile
import unittest

try:
	import settings as fw_settings
except ImportError:            # settings.py imports cv2, which a bare test env may lack
	fw_settings = None

import modes


@unittest.skipIf(fw_settings is None, 'needs opencv (settings.py imports cv2)')
class SettingsTests(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self._orig = fw_settings.SETTINGS_PATH
		fw_settings.SETTINGS_PATH = os.path.join(self.tmp.name, 'settings.json')
		self.addCleanup(setattr, fw_settings, 'SETTINGS_PATH', self._orig)

	def test_defaults_start_in_control_mode(self):
		self.assertEqual(fw_settings.DEFAULTS['mode'], modes.CONTROL)
		self.assertEqual(fw_settings.load_settings()['mode'], modes.CONTROL)

	def test_mode_and_debug_are_session_only(self):
		s = fw_settings.load_settings()
		s.update(mode=modes.PAINT, debug=True, music_key='D')
		fw_settings.save_settings(s)
		with open(fw_settings.SETTINGS_PATH) as f:
			on_disk = json.load(f)
		self.assertNotIn('mode', on_disk)
		self.assertNotIn('debug', on_disk)
		again = fw_settings.load_settings()
		self.assertEqual(again['mode'], modes.CONTROL, 'every launch starts in Control mode')
		self.assertFalse(again['debug'])

	def test_music_choices_persist(self):
		s = fw_settings.load_settings()
		s.update(music_key='F#', music_scale='Dorian', music_instrument='theremin')
		fw_settings.save_settings(s)
		again = fw_settings.load_settings()
		self.assertEqual((again['music_key'], again['music_scale'], again['music_instrument']),
			('F#', 'Dorian', 'theremin'))

	def test_a_stale_mode_in_an_old_settings_file_is_ignored(self):
		with open(fw_settings.SETTINGS_PATH, 'w') as f:
			json.dump({'mode': 'music', 'sensitivity': 1.5}, f)
		s = fw_settings.load_settings()
		self.assertEqual(s['mode'], modes.CONTROL)
		self.assertEqual(s['sensitivity'], 1.5)


class ModesTests(unittest.TestCase):
	def test_normalizers_fall_back_safely(self):
		self.assertEqual(modes.normalize_mode('bogus'), modes.CONTROL)
		self.assertEqual(modes.normalize_mode(None), modes.CONTROL)
		self.assertEqual(modes.normalize_mode('paint'), modes.PAINT)
		self.assertEqual(modes.normalize_instrument('bogus'), 'harp')
		self.assertEqual(modes.normalize_instrument('keys'), 'keys')
		self.assertFalse(modes.is_art_mode(modes.CONTROL))
		self.assertTrue(modes.is_art_mode(modes.PAINT) and modes.is_art_mode(modes.MUSIC))

	def test_old_string_instrument_names_map_to_strings(self):
		# earlier versions had violin / viola / cello; a remembered choice must still work
		for old in ('violin', 'viola', 'cello'):
			self.assertEqual(modes.normalize_instrument(old), 'strings')
		self.assertIn('strings', modes.INSTRUMENT_IDS)
		for gone in ('violin', 'viola', 'cello'):
			self.assertNotIn(gone, modes.INSTRUMENT_IDS)

	def test_every_mode_and_instrument_is_described(self):
		self.assertEqual(modes.MODE_IDS, ['control', 'paint', 'music'])
		for mode_id, label, blurb in modes.MODES:
			self.assertTrue(label and blurb)
		for inst_id, label, blurb in modes.INSTRUMENTS:
			self.assertTrue(label and blurb)


if __name__ == '__main__':
	unittest.main()
