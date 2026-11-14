"""Music theory helpers for Music mode. Pure functions, no audio, no Tk.

The whole design goal of Music mode is "you can't play a wrong note":
every instrument draws its notes from the chosen key + scale, and the left
hand picks chords from that same key, so whatever the right hand does
lands somewhere musical.
"""

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Intervals in semitones above the root. Pentatonic scales come first
# because they're the friendliest: any notes of one played in any order
# sound fine together, which is exactly what flailing a hand through the
# air needs.
SCALES = {
	'Major pentatonic': [0, 2, 4, 7, 9],
	'Minor pentatonic': [0, 3, 5, 7, 10],
	'Major': [0, 2, 4, 5, 7, 9, 11],
	'Natural minor': [0, 2, 3, 5, 7, 8, 10],
	'Dorian': [0, 2, 3, 5, 7, 9, 10],
	'Lydian': [0, 2, 4, 6, 7, 9, 11],
	'Blues': [0, 3, 5, 6, 7, 10],
}

DEFAULT_SCALE = 'Major pentatonic'
DEFAULT_KEY = 'C'

# Four chords the left hand can pick (1-4 fingers), as (numeral, semitones
# above the key's root, quality). Both sets are the classic "four chords"
# that cover most pop songs, so switching between them with your left hand
# sounds like a song rather than an exercise.
_MAJOR_CHORDS = [('I', 0, 'maj'), ('IV', 5, 'maj'), ('V', 7, 'maj'), ('vi', 9, 'min')]
_MINOR_CHORDS = [('i', 0, 'min'), ('iv', 5, 'min'), ('VI', 8, 'maj'), ('VII', 10, 'maj')]

_TRIADS = {'maj': (0, 4, 7), 'min': (0, 3, 7)}


def key_index(name):
	"""'C#' -> 1. Unknown names fall back to C."""
	try:
		return NOTE_NAMES.index(name)
	except ValueError:
		return 0


def is_minor_scale(scale_name):
	"""A scale is 'minor-flavored' if it has a minor third and no major one."""
	intervals = SCALES.get(scale_name, SCALES[DEFAULT_SCALE])
	return 3 in intervals and 4 not in intervals


def midi_to_freq(midi):
	return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def note_name(midi):
	return NOTE_NAMES[int(round(midi)) % 12]


def chord_set(key, scale_name):
	"""The four selectable chords for this key/scale.

	Each is a dict: label (e.g. 'Am'), numeral, root_pc (0-11),
	quality ('maj'/'min')."""
	root = key_index(key) if isinstance(key, str) else int(key) % 12
	family = _MINOR_CHORDS if is_minor_scale(scale_name) else _MAJOR_CHORDS
	chords = []
	for numeral, offset, quality in family:
		pc = (root + offset) % 12
		chords.append({
			'numeral': numeral,
			'root_pc': pc,
			'quality': quality,
			'label': NOTE_NAMES[pc] + ('m' if quality == 'min' else ''),
		})
	return chords


def chord_notes(chord, count, lowest=45):
	"""`count` ascending MIDI notes cycling through the chord's triad,
	starting on its root at or above MIDI `lowest` (default A2).

	Harp strings are tuned to these, so strumming across them always
	sounds like the chord, however the hand moves."""
	root = lowest + ((chord['root_pc'] - lowest) % 12)
	triad = _TRIADS[chord['quality']]
	notes = []
	octave = 0
	while len(notes) < count:
		for interval in triad:
			notes.append(root + octave * 12 + interval)
			if len(notes) == count:
				break
		octave += 1
	return notes


def scale_notes(key, scale_name, count, lowest=60):
	"""`count` ascending MIDI notes of the scale, the first being the key's
	root at or above MIDI `lowest` (default middle C). Used for the Keys
	instrument's key layout and the Theremin's snap points."""
	root_pc = key_index(key) if isinstance(key, str) else int(key) % 12
	intervals = SCALES.get(scale_name, SCALES[DEFAULT_SCALE])
	root = lowest + ((root_pc - lowest) % 12)
	notes = []
	octave = 0
	while len(notes) < count:
		for interval in intervals:
			notes.append(root + octave * 12 + interval)
			if len(notes) == count:
				break
		octave += 1
	return notes


def snap_to_scale(midi, key, scale_name, strength=1.0):
	"""Pull a continuous MIDI pitch toward the nearest scale note.
	strength 0 = untouched, 1 = fully snapped."""
	root_pc = key_index(key) if isinstance(key, str) else int(key) % 12
	intervals = SCALES.get(scale_name, SCALES[DEFAULT_SCALE])
	base = int(midi // 12) * 12
	best = None
	for octave in (-12, 0, 12):
		for interval in intervals:
			cand = base + octave + (root_pc + interval) % 12
			# (root_pc + interval) % 12 loses the carry past an octave, so
			# test every neighbouring octave and keep the closest.
			if best is None or abs(cand - midi) < abs(best - midi):
				best = cand
	return midi + (best - midi) * strength
