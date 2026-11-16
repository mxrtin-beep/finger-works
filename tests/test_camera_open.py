import sys
import unittest
from unittest import mock

try:
	import main_fast
except Exception:          # needs OpenCV, MediaPipe, pyautogui and a display; skip where unavailable
	main_fast = None


class FakeCap:
	"""A VideoCapture stand-in that opens only on the backends in `opens_on`,
	and returns frames only on those in `delivers_on` (default: the same)."""
	instances = []

	def __init__(self, device, backend, opens_on, log, delivers_on=None):
		self.device, self.backend = device, backend
		self._open = backend in opens_on
		self._delivers = self._open if delivers_on is None else backend in delivers_on
		self.released = False
		self.props = {}
		log.append(backend)
		FakeCap.instances.append(self)

	def isOpened(self):
		return self._open

	def read(self):
		return (True, object()) if self._delivers else (False, None)

	def release(self):
		self.released = True
		self._open = False        # like a real VideoCapture: released means not opened

	def set(self, prop, value):
		self.props[prop] = value
		return True


_real_delivers = getattr(main_fast, '_camera_delivers_frame', None)


@unittest.skipIf(main_fast is None, 'needs the full app dependencies (cv2, mediapipe, pyautogui, a display)')
class OpenCameraTests(unittest.TestCase):
	def run_open(self, platform, opens_on_by_pass, delivers_on=None):
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
			return FakeCap(device, backend, current['set'], log, delivers_on)

		with mock.patch.object(sys, 'platform', platform), \
				mock.patch.object(cv2, 'VideoCapture', factory), \
				mock.patch.object(main_fast.time, 'sleep') as sleep, \
				mock.patch.object(main_fast, '_camera_delivers_frame', lambda c: _real_delivers(c, seconds=0.0)):
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

	def test_a_backend_that_opens_but_never_delivers_a_frame_is_skipped(self):
		# the failure behind "the program doesn't open": the fallback backend
		# reported opened, then every read failed, and the app quietly quit
		cv2 = main_fast.cv2
		cap, log, _ = self.run_open('win32', [{cv2.CAP_DSHOW, cv2.CAP_ANY}], delivers_on={cv2.CAP_ANY})
		self.assertTrue(cap.isOpened())
		self.assertEqual(cap.backend, cv2.CAP_ANY, 'DirectShow opened but gave no frames; the default backend is used')
		self.assertTrue(FakeCap.instances[0].released)

	def test_open_but_dead_everywhere_is_a_failure_not_a_success(self):
		cv2 = main_fast.cv2
		cap, log, _ = self.run_open('win32', [{cv2.CAP_DSHOW, cv2.CAP_ANY}, {cv2.CAP_DSHOW, cv2.CAP_ANY}], delivers_on=set())
		self.assertFalse(cap.isOpened(), 'a camera that never yields a frame must not be handed back as working')

	def test_other_platforms_never_use_the_windows_only_backend(self):
		cv2 = main_fast.cv2
		for platform in ('linux', 'darwin'):
			cap, log, _ = self.run_open(platform, [{cv2.CAP_ANY}])
			self.assertTrue(cap.isOpened())
			self.assertEqual(log, [cv2.CAP_ANY], platform)


if __name__ == '__main__':
	unittest.main()


class DeliversFrameTests(unittest.TestCase):
	@unittest.skipIf(main_fast is None, 'needs the full app dependencies')
	def test_waits_through_failed_reads_then_succeeds(self):
		class Slow:
			def __init__(self):
				self.calls = 0
			def read(self):
				self.calls += 1
				return (self.calls > 4, object())
		cap = Slow()
		with mock.patch.object(main_fast.time, 'sleep'):
			self.assertTrue(main_fast._camera_delivers_frame(cap, seconds=5.0))
		self.assertEqual(cap.calls, 5)

	@unittest.skipIf(main_fast is None, 'needs the full app dependencies')
	def test_gives_up_after_the_deadline(self):
		class Dead:
			def read(self):
				return False, None
		clock = iter([0.0, 0.5, 1.0, 1.6, 2.1, 9.0, 9.0, 9.0])
		with mock.patch.object(main_fast.time, 'time', lambda: next(clock)), mock.patch.object(main_fast.time, 'sleep'):
			self.assertFalse(main_fast._camera_delivers_frame(Dead(), seconds=2.0))
