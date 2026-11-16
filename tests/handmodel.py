"""Builds synthetic hands for gesture tests.

Geometry is expressed in "hand-scale units" (wrist -> middle knuckle = 1.0),
the same normalization the app applies before comparing against the cutoffs
in constants.py, so a finger that's `out` here really is past
FINGER_OUT_CUTOFF and a `pinch` really is inside LEFT/RIGHT_CLICK_CUTOFF.
"""

import numpy as np

import art_gestures as ag

# (x right, y up) of each landmark's base joint / tip, in hand-scale units.
_MCP = {1: (-0.25, 0.15), 5: (-0.30, 0.95), 9: (0.0, 1.0), 13: (0.28, 0.95), 17: (0.52, 0.80)}
_OUT = {4: (-1.15, 1.0), 8: (-0.35, 1.95), 12: (0.0, 2.05), 16: (0.30, 1.95), 20: (0.60, 1.70)}
_FOLD = {4: (-0.6, 0.35), 8: (-0.2, 0.5), 12: (0.0, 0.55), 16: (0.25, 0.5), 20: (0.4, 0.45)}
_CHAIN = {4: (1, 2, 3), 8: (5, 6, 7), 12: (9, 10, 11), 16: (13, 14, 15), 20: (17, 18, 19)}
_TIPS = [4, 8, 12, 16, 20]

# Poses as [thumb, index, middle, ring, pinky] extended flags.
FIST = (0, 0, 0, 0, 0)
ONE = (0, 1, 0, 0, 0)
TWO = (0, 1, 1, 0, 0)
THREE = (0, 1, 1, 1, 0)
FOUR = (0, 1, 1, 1, 1)
OPEN = (1, 1, 1, 1, 1)
THUMB = (1, 0, 0, 0, 0)
SHAKA = (1, 0, 0, 0, 1)

FRAME_W, FRAME_H = 640, 480
SCALE_PX = 110.0


def make_hand(label='Right', cx=330.0, cy=330.0, out=FIST, pinch=None, roll=0.0):
	"""A Hand with its wrist at camera pixel (cx, cy).

	`pinch`: None, 'index' / 'ring' (thumb touching that fingertip), or
	'near_index' (thumb and index about to touch, same midpoint)."""
	tips = {tip: (_OUT if out[i] else _FOLD)[tip] for i, tip in enumerate(_TIPS)}
	if pinch == 'near_index':
		tips[4], tips[8] = (-0.38, 0.95), (-0.38, 1.47)
	elif pinch == 'index':
		tips[4], tips[8] = (-0.4, 1.2), (-0.36, 1.22)
	elif pinch == 'ring':
		tips[4], tips[16] = (0.1, 1.1), (0.12, 1.12)

	local = {0: (0.0, 0.0)}
	for tip, (j1, j2, j3) in _CHAIN.items():
		base = _MCP[j1]
		end = tips[tip]
		local[j1] = base
		local[j2] = (base[0] + (end[0] - base[0]) / 3, base[1] + (end[1] - base[1]) / 3)
		local[j3] = (base[0] + 2 * (end[0] - base[0]) / 3, base[1] + 2 * (end[1] - base[1]) / 3)
		local[tip] = end

	if roll:
		# tilt the whole hand about the wrist; positive leans toward +x (the user's right)
		a = np.radians(roll)
		local = {i: (x * np.cos(a) + y * np.sin(a), -x * np.sin(a) + y * np.cos(a)) for i, (x, y) in local.items()}

	abs_lm = np.zeros((21, 3))
	rel_lm = np.zeros((21, 3))
	for i in range(21):
		x, y = local[i]
		abs_lm[i] = (cx + x * SCALE_PX, cy - y * SCALE_PX, 0.0)
		rel_lm[i] = (x, -y, 0.0)      # wrist-relative, image axes (y down), already /scale
	return ag.Hand(label, abs_lm, rel_lm, FRAME_W, FRAME_H)
