"""The ways FingerWorks can be used. Dependency-free so every other module
(overlay, main loop, the art sessions, settings) can import it without
risking an import cycle."""

CONTROL = 'control'
PAINT = 'paint'
MUSIC = 'music'

# (id, label, one-line description) -- display order.
MODES = [
	(CONTROL, 'Control', 'Move the cursor, click, type, zoom and scroll -- your hands run the computer.'),
	(PAINT, 'Paint', 'Paint with living light: pinch to ignite, clench to gather, snap open to burst; tilt your left hand to tune.'),
	(MUSIC, 'Music', 'Play an instrument in the air: strum a harp, play keys, or wave a theremin.'),
]

MODE_IDS = [m[0] for m in MODES]
MODE_LABELS = {m[0]: m[1] for m in MODES}

# Instruments inside Music mode -- display order. The first is the default.
INSTRUMENTS = [
	('harp', 'Harp', 'Sweep your index finger across the strings to strum.'),
	('keys', 'Keys', 'Pinch over a key to play it; slide while pinched for a glissando.'),
	('theremin', 'Theremin', 'Move your hand left/right for pitch. Fist = silence.'),
]

INSTRUMENT_IDS = [i[0] for i in INSTRUMENTS]
INSTRUMENT_LABELS = {i[0]: i[1] for i in INSTRUMENTS}
DEFAULT_INSTRUMENT = INSTRUMENT_IDS[0]


def is_art_mode(mode):
	return mode in (PAINT, MUSIC)


def normalize_mode(mode):
	return mode if mode in MODE_IDS else CONTROL


def normalize_instrument(name):
	return name if name in INSTRUMENT_IDS else DEFAULT_INSTRUMENT
