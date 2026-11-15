import sys
import unittest
from unittest import mock

try:
	import main_fast
except Exception:          # needs OpenCV, MediaPipe, pyautogui and a display; skip where unavailable
	main_fast = None


class FakeCap:
	"""A VideoCapture stand-in that opens only on the backends in `opens_on`."""
	instances = []

	def __init__(self, device, backend, opens_on, log):
		self.device, self.backend = device, backend
		self._open = backend in opens_on
		self.released = False
		self.props = {}
		log.append(backend)
		FakeCap.instances.append(self)

	def isOpened(self):
		return self._open

	def release(self):
		self.released = True

	def set(self, prop, value):
		self.props[prop] = value
		return True


@unittest.skipIf(main_fast is None, 'needs the full app dependencies (cv2, mediapipe, pyautogui, a display)')
class OpenCameraTests(unittest.TestCase):
	def run_open(self, platform, opens_on_by_pass):
		"""opens_on_by_pass: list (one per pass) of the set of backends that open on that pass."""
		log, passes = [], iter(opens_on_by_pass)
		current = {'set': set()}
		FakeCap.instances.clear()
		cv2 = main_fast.cv2
		started = {'n': 0}

		def factory(device, backend=cv2.CAP_ANY):
			# a new pass starts whenever the backend list wraps back to its first entry
			first = cv2.CAP_DSHOW if platform == 'win32' else cv2.CAP_ANY
			if backend == first and (not log or len(log) % len(self.backends(platform)) == 0):
				current['set'] = next(passes, set())
			return FakeCap(device, backend, current['set'], log)

		with mock.patch.object(sys, 'platform', platform), \
				mock.patch.object(cv2, 'VideoCapture', factory), \
				mock.patch.object(main_fast.time, 'sleep') as sleep:
			cap = main_fast._open_camera(0, 1280, 720)
		return cap, log, sleep

	def backends(self, platform):
		cv2 = main_fast.cv2
		return [cv2.CAP_DSHOW, cv2.CAP_ANY] if platform == 'win32' else [cv2.CAP_ANY]

	def test_directshow_works_first_try(self):
		cv2 = main_fast.cv2
		cap, log, sleep = self.run_open('win32', [{cv2.CAP_DSHOW, cv2.CAP_ANY}])
		self.assertTrue(cap.isOpened())
		self.assertEqual(log, [cv2.CAP_DSHOW])
		self.assertEqual(cap.props[cv2.CAP_PROP_FRAME_WIDTH], 1280)
		sleep.assert_not_called()

	def test_falls_back_to_the_default_backend_when_directshow_fails(self):
		# the reported case: DirectShow fails, the default backend opens the camera
		cv2 = main_fast.cv2
		cap, log, sleep = self.run_open('win32', [{cv2.CAP_ANY}])
		self.assertTrue(cap.isOpened())
		self.assertEqual(log, [cv2.CAP_DSHOW, cv2.CAP_ANY])
		self.assertTrue(FakeCap.instances[0].released, 'the failed attempt is released, not leaked')
		sleep.assert_not_called()

	def test_retries_once_after_a_pause_when_the_camera_is_briefly_busy(self):
		cv2 = main_fast.cv2
		cap, log, sleep = self.run_open('win32', [set(), {cv2.CAP_DSHOW}])
		self.assertTrue(cap.isOpened())
		self.assertEqual(len(log), 3)
		sleep.assert_called_once()

	def test_gives_up_cleanly_when_nothing_opens(self):
		cap, log, sleep = self.run_open('win32', [set(), set()])
		self.assertFalse(cap.isOpened(), 'callers check isOpened() and raise their clear error')
		self.assertEqual(len(log), 4)
		self.assertTrue(all(c.released for c in FakeCap.instances[:-1]))

	def test_other_platforms_never_use_the_windows_only_backend(self):
		cv2 = main_fast.cv2
		for platform in ('linux', 'darwin'):
			cap, log, _ = self.run_open(platform, [{cv2.CAP_ANY}])
			self.assertTrue(cap.isOpened())
			self.assertEqual(log, [cv2.CAP_ANY], platform)


if __name__ == '__main__':
	unittest.main()
