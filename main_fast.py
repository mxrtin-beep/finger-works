
import datetime
import os
import time
import urllib.request

import cv2
import mediapipe as mp
import pyautogui
import pyperclip
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
	HandLandmarker,
	HandLandmarkerOptions,
	RunningMode,
)
import numpy as np
from collections import deque

import mouse_control as mc
from mouse_control import execute_event_fast, screenWidth, screenHeight
from event_classifier import get_event_fast, get_zoom_event, get_paste_event, is_zoomed_in
import constants as c
import keyboard as k
import overlay as ov
import settings as fw_settings


__version__ = '0.2.0'

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hand_landmarker.task')
MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'


def ensure_model_downloaded(model_path=MODEL_PATH, model_url=MODEL_URL):
	"""Download the HandLandmarker task model if it isn't already on disk."""
	if not os.path.exists(model_path):
		print(f'Downloading hand landmarker model to {model_path}...')
		urllib.request.urlretrieve(model_url, model_path)
	return model_path


width = 1440
height = 900

play_audio = False
history_length = 8
event_history = deque(maxlen=history_length)


# The 21 hand-landmark connections drawn for the debug video's hand
# skeleton -- the same topology mediapipe's own drawing_utils.HAND_CONNECTIONS
# uses (thumb/index/middle/ring/pinky chains off the wrist, plus the palm
# connections tying the finger bases together), just hardcoded here since
# we're drawing over plain landmark lists (the Tasks API's HandLandmarker
# output) rather than the legacy mp.solutions.hands proto type that
# draw_landmarks() expects.
_HAND_CONNECTIONS = [
	(0, 1), (1, 2), (2, 3), (3, 4),          # thumb
	(0, 5), (5, 6), (6, 7), (7, 8),          # index
	(5, 9), (9, 10), (10, 11), (11, 12),     # middle
	(9, 13), (13, 14), (14, 15), (15, 16),   # ring
	(13, 17), (17, 18), (18, 19), (19, 20),  # pinky
	(0, 17),                                 # palm base
]

# Debug-only: BGR-ish colors (fine either way round, both channels equal or
# distinct enough to read) used to trace each hand's skeleton and label its
# current gesture in the live debug video -- purely cosmetic, doesn't affect
# mouse/keyboard control at all.
_RIGHT_HAND_COLOR = (255, 210, 0)   # cyan-ish -- the mouse/keyboard hand
_LEFT_HAND_COLOR = (255, 0, 220)    # magenta-ish -- the zoom/paste hand


def draw_hand_debug_overlay(image, abs_landmark_list, label, color):
	"""Trace a hand's skeleton and label its current gesture directly onto
	`image` (mutated in place) -- shown in the --debug live camera window.
	Purely cosmetic: it has no effect on how gestures are recognized or
	acted on, only on what the debug window shows while they happen."""
	points = [(int(p[0]), int(p[1])) for p in abs_landmark_list]

	for start, end in _HAND_CONNECTIONS:
		cv2.line(image, points[start], points[end], color, 2)
	for x, y in points:
		cv2.circle(image, (x, y), 4, color, -1)

	if label:
		wrist_x, wrist_y = points[0]
		cv2.putText(
			image, label, (max(0, wrist_x - 40), wrist_y + 30),
			cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA,
		)


def calc_landmark_list(image, landmarks):
	image_width, image_height = image.shape[1], image.shape[0]

	landmark_point = []

	# Keypoint
	# NOTE: `landmarks` is a plain list of NormalizedLandmark objects, as
	# returned per-hand by the HandLandmarker Tasks API (no `.landmark`
	# wrapper like the old `mp.solutions.hands` API used).
	for landmark in landmarks:
		landmark_x = min(int(landmark.x * image_width), image_width - 1)
		landmark_y = min(int(landmark.y * image_height), image_height - 1)
		landmark_z = landmark.z

		landmark_point.append([landmark_x, landmark_y, landmark_z])

	return landmark_point



def pre_process_landmark(landmark_list):

	# Work on a copy: this function mutates entries in place, and since
	# Python lists are passed by reference, mutating the caller's list
	# here would silently corrupt their `abs_landmark_list` (which needs
	# to stay in true image-pixel coordinates) into these wrist-relative
	# ones. That aliasing bug is what broke the keyboard's hit-testing.
	landmark_list = [point[:] for point in landmark_list]

	base_x, base_y = landmark_list[0][0], landmark_list[0][1]

	for i in range(len(landmark_list)):
		landmark_list[i][0] -= base_x
		landmark_list[i][1] -= base_y

	#maxval = max(max(x) for x in landmark_list)
	#minval = min(min(x) for x in landmark_list)

	#max_value = float(max(maxval, -minval))
	max_value = 1

	for i in range(len(landmark_list)):
		landmark_list[i][0] = float(landmark_list[i][0]) / max_value
		landmark_list[i][1] = float(landmark_list[i][1]) / max_value
	return landmark_list


def copy_or_cut_typed_buffer(typed_text, should_clear):
	"""Copy the keyboard's own typed-text buffer (the text after the '>'
	on the overlay) to the OS clipboard, and optionally clear it -- this
	is a separate, smaller scratchpad of what you've typed *here*,
	distinct from the 'Copy'/'Cut' keys which act on whatever's selected
	elsewhere on the desktop."""
	content = typed_text[1:] if typed_text.startswith('>') else typed_text
	pyperclip.copy(content)
	return '>' if should_clear else typed_text


def type_char(typed_char, typed_text):
	"""Send a real keystroke (or clipboard hotkey) to whatever window has
	OS focus, and return the updated local preview-text string shown on
	the overlay (which is just an echo/log for feedback -- the real
	destination of every keystroke is the focused app, not this string)."""

	if typed_char == '<':
		pyautogui.press('backspace')
		return typed_text[:-1]

	if typed_char == 'Space':
		pyautogui.press('space')
		return typed_text + ' '

	if typed_char == 'Clear':
		# Only clears our own preview line -- there's no general way to
		# clear whatever's focused elsewhere on the desktop.
		return ''

	if typed_char == 'Copy':
		# No way around simulating the real shortcut here -- only the
		# focused app knows what's currently selected, so it has to do the
		# actual copying into the OS clipboard itself.
		pyautogui.hotkey('ctrl', 'c')
		return typed_text

	if typed_char == 'Cut':
		pyautogui.hotkey('ctrl', 'x')
		return typed_text

	if typed_char == 'Copy Typed':
		return copy_or_cut_typed_buffer(typed_text, should_clear=False)

	if typed_char == 'Cut Typed':
		return copy_or_cut_typed_buffer(typed_text, should_clear=True)

	if typed_char == 'Paste':
		# Read the clipboard directly and type its contents as real
		# keystrokes, instead of simulating Ctrl+V -- this doesn't depend
		# on the focused app correctly intercepting the paste shortcut
		# (some apps use a different one, or can swallow/mishandle a
		# synthetic Ctrl+V), so it's more reliable across different apps.
		clipboard_text = pyperclip.paste()
		if clipboard_text:
			pyautogui.typewrite(clipboard_text)
		return typed_text

	# Regular character key. pyautogui.press() accepts single letters,
	# digits, and this keyboard's punctuation (',', '.', '/', ';') as
	# literal key names directly.
	pyautogui.press(typed_char.lower())

	if play_audio:
		k.say_key_pressed(typed_char)

	return typed_text + typed_char


def main(settings):

	mouse_sensitivity = settings['sensitivity']
	debug = settings['debug']

	mc.set_sensitivity_multiplier(mouse_sensitivity)

	cap_width = width
	cap_height = height

	# camera_device resolution: an explicit setting always wins; otherwise
	# auto-pick the first camera that actually opens (today's original
	# behavior, device=0, made robust against a camera that isn't there).
	available_cameras = fw_settings.list_cameras()
	cap_device = fw_settings.pick_camera_device(settings, available=available_cameras)
	# The raw setting (None means "Auto"), kept separate from `cap_device`
	# (the actual resolved index currently in use) so the Settings window
	# shows "Auto" rather than whichever index auto-pick happened to land
	# on, unless the user explicitly chose one.
	camera_device_setting = settings.get('camera_device')

	print(
		f'FingerWorks v{__version__} -- started '
		f'{datetime.datetime.now():%Y-%m-%d %H:%M:%S} '
		f'(screen {screenWidth}x{screenHeight}, camera {cap_device}, '
		f'mouse sensitivity {mouse_sensitivity}x, debug {"on" if debug else "off"})'
	)

	min_detection_confidence = c.MIN_DETECTION_CONFIDENCE
	min_tracking_confidence = c.MIN_TRACKING_CONFIDENCE

	# Camera (used only to feed the hand-tracking model -- no video window
	# is shown by default; the overlay panel and, in debug mode, the live
	# camera-feed window are the only things on screen besides whatever
	# else you're using your computer for).
	cap = cv2.VideoCapture(cap_device)
	cap.set(cv2.CAP_PROP_FRAME_WIDTH, cap_width)
	cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cap_height)

	def reopen_camera(new_device):
		"""Swap the live camera device at runtime (Settings window ->
		Apply), without restarting the program. Keeps the old camera
		running if the new one fails to open, rather than leaving `cap`
		pointing at a dead device."""
		nonlocal cap
		new_cap = cv2.VideoCapture(new_device)
		new_cap.set(cv2.CAP_PROP_FRAME_WIDTH, cap_width)
		new_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cap_height)
		if not new_cap.isOpened():
			print(f'[WARN] Could not open camera {new_device}; keeping current camera.')
			new_cap.release()
			return False
		cap.release()
		cap = new_cap
		return True

	def handle_settings_changed(new_settings):
		nonlocal cap_device, camera_device_setting
		fw_settings.save_settings(new_settings)

		mc.set_sensitivity_multiplier(new_settings['sensitivity'])
		overlay.set_sensitivity(new_settings['sensitivity'])
		overlay.set_debug(new_settings['debug'])

		resolved_device = fw_settings.pick_camera_device(new_settings)
		if resolved_device != cap_device:
			if reopen_camera(resolved_device):
				cap_device = resolved_device
				camera_device_setting = new_settings['camera_device']
		else:
			camera_device_setting = new_settings['camera_device']

	def get_current_settings():
		return {
			'camera_device': camera_device_setting,
			'sensitivity': overlay.mouse_sensitivity,
			'debug': overlay.debug,
		}

	model_path = ensure_model_downloaded()

	base_options = BaseOptions(model_asset_path=model_path)
	options = HandLandmarkerOptions(
		base_options=base_options,
		running_mode=RunningMode.VIDEO,
		# Two hands: the right hand drives the mouse/keyboard as before,
		# and the left hand is free for the zoom gesture (see below) --
		# so the right hand isn't overloaded with yet another gesture to
		# distinguish from clicking/typing.
		num_hands=2,
		min_hand_detection_confidence=min_detection_confidence,
		min_hand_presence_confidence=min_detection_confidence,
		min_tracking_confidence=min_tracking_confidence,
	)
	landmarker = HandLandmarker.create_from_options(options)

	# detect_for_video requires monotonically increasing timestamps.
	start_time_ms = int(time.time() * 1000)

	event = ''
	control_state = 'Mouse'	# Mouse or Keyboard
	typed_text = '>'

	overlay = ov.Overlay(
		screenWidth, screenHeight, debug=debug, mouse_sensitivity=mouse_sensitivity,
		on_settings_changed=handle_settings_changed,
		get_settings=get_current_settings,
		get_available_cameras=fw_settings.list_cameras,
	)

	# The keyboard's layout is now sized to the overlay panel (fixed at
	# startup), not the camera frame, so it only needs to be built once.
	button_list = k.get_button_list(overlay.panel_width, overlay.panel_height)

	try:
		while event != 'Quit' and not overlay.should_quit:

			ret, image = cap.read()
			if not ret:
				break
			image = cv2.flip(image, 1)  # Mirror display

			frame_height, frame_width = image.shape[:2]

			image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

			if overlay.paused:
				# Skip hand detection/gesture processing entirely while
				# paused (saves the model's per-frame cost too) -- just
				# keep the UI responsive and, in debug mode, still show the
				# raw camera feed so it's clear the camera itself is still
				# working.
				overlay.draw(event, control_state, typed_text, button_list)
				if overlay.debug:
					overlay.draw_video(image)
				overlay.pump()
				continue

			mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image)
			timestamp_ms = int(time.time() * 1000) - start_time_ms
			results = landmarker.detect_for_video(mp_image, timestamp_ms)

			hand_debug_text = ''

			if results.hand_landmarks:

				# Which hand does what is strictly by hand identity --
				# right hand mouses/types, left hand zooms/pastes --
				# regardless of how many hands are in frame. This is
				# MediaPipe's own per-hand Left/Right classification
				# (each hand is classified independently of whether a
				# second hand is present, so there's no reason a single
				# visible hand should be treated any differently than
				# one of a pair); constants.SWAP_LABELED_HANDS flips it
				# wholesale if it's ever backwards for your camera setup.
				# A hand-rolled geometry-based classifier was tried
				# instead of trusting this label, and came out less
				# reliable, not more, so it's gone.
				debug_parts = []
				mouse_assigned = False

				for hand_idx, hand_landmarks in enumerate(results.hand_landmarks):
					abs_landmark_list = np.array(calc_landmark_list(image, hand_landmarks))
					rel_landmark_list = np.array(pre_process_landmark(abs_landmark_list.tolist()))

					raw_label = results.handedness[hand_idx][0].category_name
					if c.SWAP_LABELED_HANDS:
						raw_label = 'Left' if raw_label == 'Right' else 'Right'

					if raw_label == 'Left':
						zoom_event, zoom_debug_text = get_zoom_event(rel_landmark_list)
						if zoom_event == 'Zoom In':
							mc.execute_zoom('in')
							mc.set_zoomed(True)
							zoom_debug_text += ' -> sent zoom-in'
						elif zoom_event == 'Zoom Out':
							mc.execute_zoom('out')
							mc.set_zoomed(False)
							zoom_debug_text += ' -> sent zoom-out'

						paste_fired, paste_debug_text = get_paste_event(rel_landmark_list)
						if paste_fired:
							# "Scissors" pose (index + middle extended) --
							# the same shape as the right hand's Cut-Typed
							# gesture, but paste on this (left) hand: a
							# shortcut for the keyboard's 'Paste' key
							# without needing the keyboard open at all.
							typed_text = type_char('Paste', typed_text)

						debug_parts.append(
							f'Left [Zoom: {zoom_debug_text}] [Paste: {paste_debug_text}]'
						)

						if overlay.debug:
							draw_hand_debug_overlay(
								image, abs_landmark_list,
								f'Zoom: {zoom_debug_text.split(" -> ")[0]}  Paste: {paste_debug_text.split(" -> ")[0]}',
								_LEFT_HAND_COLOR,
							)

						continue

					# raw_label == 'Right'
					if mouse_assigned:
						# A second hand also read as 'Right' (shouldn't
						# normally happen) -- ignored rather than fighting
						# over the cursor with the hand already driving it.
						debug_parts.append('Right [ignored]')
						continue
					mouse_assigned = True
					debug_parts.append('Right [Mouse]')

					event = get_event_fast(abs_landmark_list, rel_landmark_list, control_state)

					event_history.append(event)

					if event == 'Keyboard On':
						control_state = 'Keyboard'
					elif event == 'Keyboard Off':
						control_state = 'Mouse'
					elif event == 'Cut Typed Gesture':
						# Gesture shortcut for the 'Cut Typed' key: index +
						# middle extended ("scissors"), cutting the
						# keyboard's typed-text buffer without needing to
						# aim at that specific key.
						typed_text = copy_or_cut_typed_buffer(typed_text, should_clear=True)

					# Always drive the real OS cursor so it tracks your
					# finger in both modes (so it visually hovers over the
					# overlay's keys too). Whether the pinch also clicks
					# the real desktop is decided below, per-frame, rather
					# than solely by Mouse-vs-Keyboard mode -- so you can
					# still click things while the keyboard is open, as
					# long as you're not currently aiming at one of its
					# keys (see hit_button below).
					hit_button = None
					if control_state == 'Keyboard':
						mouse_screen_pos = pyautogui.position()
						button_list, typed_char, hit_button = k.execute_event_keyboard(
							event, mouse_screen_pos, overlay.origin(), button_list
						)

						if typed_char is not None:
							typed_text = type_char(typed_char, typed_text)

					# Click the real desktop when in Mouse mode, or in
					# Keyboard mode as long as the cursor isn't over a key
					# (that pinch was just consumed above as a keypress
					# instead).
					allow_click = (control_state == 'Mouse') or (hit_button is None)

					execute_event_fast(
						event, abs_landmark_list, event_history,
						frame_width, frame_height,
						allow_click=allow_click,
					)

					if overlay.debug:
						draw_hand_debug_overlay(
							image, abs_landmark_list, event, _RIGHT_HAND_COLOR,
						)

				hand_debug_text = f'  [{", ".join(debug_parts)}]'

			# Debug aid: show which detected hand is doing what right next
			# to the current action, so you can see at a glance whether
			# it's routing your hands the way you expect (see
			# constants.SWAP_LABELED_HANDS if it isn't).
			overlay.draw(event + hand_debug_text, control_state, typed_text, button_list)

			if overlay.debug:
				# Purely cosmetic: the live camera feed with each hand's
				# skeleton traced and its current gesture labeled, shown in
				# its own always-on-top debug window. `image` is already
				# RGB (converted above for MediaPipe) and now also carries
				# whatever skeleton/labels were drawn onto it above.
				overlay.draw_video(image)
			overlay.pump()

	finally:
		if is_zoomed_in():
			# Leave the OS screen magnifier back at its normal zoom level
			# rather than exiting mid-zoom -- otherwise the last thing
			# this program did stays in effect (a zoomed-in desktop) even
			# after it's no longer running to zoom back out for you.
			mc.execute_zoom('out')
			mc.set_zoomed(False)
		cap.release()
		overlay.close()
		landmarker.close()




if __name__ == '__main__':
	import argparse

	parser = argparse.ArgumentParser(description='FingerWorks -- touchless computer control via webcam.')
	parser.add_argument(
		'--sensitivity', type=float, default=None, metavar='MULTIPLIER',
		help=(
			'Mouse-speed multiplier. Defaults to whatever is saved in '
			'settings (1.0 the first time this is run); e.g. 1.5 moves the '
			'cursor faster, 0.5 slower. Overrides (and is then saved as) '
			'the settings-file value; also changeable at runtime from the '
			'Settings window.'
		),
	)
	parser.add_argument(
		'--debug', action='store_true', default=None,
		help=(
			'Show the debug overlay text (current event, mouse sensitivity, '
			'which hand is doing what, zoom/paste gesture state) plus a '
			'live camera window with each hand\'s skeleton traced and its '
			'gesture labeled, and keep the overlay panel visible at all '
			"times. Defaults to whatever is saved in settings (off the "
			'first time this is run). Overrides (and is then saved as) the '
			'settings-file value; also toggleable at runtime from the '
			'Settings window.'
		),
	)
	args = parser.parse_args()

	settings = fw_settings.load_settings()
	if args.sensitivity is not None:
		settings['sensitivity'] = args.sensitivity
	if args.debug is not None:
		settings['debug'] = args.debug

	main(settings)

