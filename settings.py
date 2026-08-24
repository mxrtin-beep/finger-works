
import json
import os

import cv2


# Stored next to the user's home directory rather than inside the repo, so
# settings survive a `git pull`/reinstall and don't show up as a dirty file
# in the working tree. A dotfile, matching the convention of similar small
# desktop tools that don't warrant a full platformdirs-style config path.
SETTINGS_PATH = os.path.join(os.path.expanduser('~'), '.finger_works_settings.json')

# camera_device: None means "auto-pick" (today's default behavior -- the
# first camera that actually opens). Anything else is an explicit index the
# user chose in the Settings window, which overrides auto-pick until they
# set it back to Auto.
DEFAULTS = {
	'camera_device': None,
	'sensitivity': 1.0,
	'debug': False,
	# Multiplies constants.SCROLL_AMOUNT -- see mouse_control's
	# set_scroll_speed_multiplier(). 1.0 = default speed.
	'scroll_speed': 1.0,
	# Multiplies the overlay panel's (and so the on-screen keyboard's) base
	# size -- see overlay.Overlay.set_keyboard_scale(). 1.0 = default size.
	'keyboard_scale': 1.0,
	# 0.0 (max smoothing, steadiest but can feel like the cursor is
	# "sliding") to 1.0 (max snappiness, tracks the fingertip almost
	# immediately but shows more raw hand-tracking jitter) -- see
	# mouse_control.set_cursor_snappiness(). Starts low/smooth, matching
	# this project's original (pre-Settings) hardcoded behavior.
	'cursor_snappiness': 0.2,
}


def load_settings():
	"""Read settings.json if it exists, filling in defaults for anything
	missing/invalid rather than failing -- a corrupt or hand-edited
	settings file should degrade to defaults, not crash startup."""
	if not os.path.exists(SETTINGS_PATH):
		return dict(DEFAULTS)

	try:
		with open(SETTINGS_PATH) as f:
			data = json.load(f)
	except (OSError, json.JSONDecodeError) as exc:
		print(f'[WARN] Could not read {SETTINGS_PATH} ({exc}); using defaults.')
		return dict(DEFAULTS)

	settings = dict(DEFAULTS)
	for key in DEFAULTS:
		if key in data:
			settings[key] = data[key]
	return settings


def save_settings(settings):
	"""Persist settings.json. Best-effort -- a failure here (e.g. read-only
	home directory) shouldn't crash the program, just mean the next run
	falls back to defaults/CLI flags again."""
	try:
		with open(SETTINGS_PATH, 'w') as f:
			json.dump({key: settings.get(key, DEFAULTS[key]) for key in DEFAULTS}, f, indent=2)
	except OSError as exc:
		print(f'[WARN] Could not save settings to {SETTINGS_PATH}: {exc}')


def list_cameras(max_index=8, stop_at_first=False):
	"""Probe camera indices 0..max_index-1 and return the ones that
	actually open. Opens and immediately releases each one, so this is
	slow-ish (each open can take several hundred ms depending on the OS's
	camera backend) -- call it when the Settings window opens (so it can
	show every camera), not once per frame.

	`stop_at_first=True` returns as soon as one opens, without probing the
	rest -- used by pick_camera_device()'s auto-pick, which only ever
	wants the first one anyway; probing every remaining index too (most of
	which don't exist and are individually slow to fail) is exactly what
	made startup noticeably slower once auto-pick was added."""
	available = []
	for idx in range(max_index):
		cap = cv2.VideoCapture(idx)
		if cap.isOpened():
			available.append(idx)
			cap.release()
			if stop_at_first:
				return available
		else:
			cap.release()
	return available


def pick_camera_device(settings, available=None):
	"""Resolve the camera device index to actually use. An explicit
	`camera_device` setting always wins and skips probing entirely;
	otherwise auto-pick the first camera that opens (today's existing
	default behavior), falling back to plain 0 if nothing was detected as
	open so a probing glitch doesn't crash startup outright.

	Pass `available` (e.g. from a Settings-window camera list already on
	hand) to skip a redundant probe; otherwise auto-pick probes just far
	enough to find the first working camera, not every index."""
	if settings.get('camera_device') is not None:
		return settings['camera_device']

	if available is None:
		available = list_cameras(stop_at_first=True)
	return available[0] if available else 0
