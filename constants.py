

THUMB_IDX = 4
INDEX_IDX = 8
MIDDLE_IDX = 12
RING_IDX = 16
PINKY_IDX = 20

FINGER_NAMES = ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']
FINGER_INDICES = [4, 8, 12, 16, 20]
#FINGER_OUT_CUTOFF = 2.5e4

FINGER_OUT_CUTOFF = 280


# Max thumb-to-fingertip pixel distance (in the camera frame) that counts
# as a pinch/click. Raised from 50 -- at 50, registering a click required
# pressing the thumb and index almost fully together, hard enough that it
# dragged the rest of the hand (including the middle finger, which aims
# the cursor) along with it. Higher = lighter tap triggers a click, but
# too high risks false clicks from your hand's normal resting pose while
# just aiming/hovering. This is a fine line and worth retuning for your
# own hand/camera setup if it still feels off in either direction.
LEFT_CLICK_CUTOFF = 70
RIGHT_CLICK_CUTOFF = 60

SCROLL_VEL_CUTOFF = 5

# Landmark index for the index finger's base knuckle (MCP joint), used
# only by the left-hand scroll gesture below to get the index finger's
# pointing *direction* (tip relative to its own base) rather than just
# whether it's extended at all.
INDEX_MCP_IDX = 5

# How many pixels (in OS-scroll units, same as pyautogui.scroll()'s
# argument) one scroll "tick" moves while the point-up/point-down gesture
# is held. Applied every SCROLL_FRAME_INTERVAL-th frame rather than every
# frame -- see SCROLL_FRAME_INTERVAL below for why.
SCROLL_AMOUNT = 40

# The point-up/point-down scroll gesture is held continuously (unlike the
# edge-triggered fist/scissors gestures), so firing a scroll tick on every
# single camera frame -- at 30fps that's up to 30 ticks/sec -- reads as an
# unpredictable, disorientating flick rather than a controlled scroll.
# Only actually sending a tick every Nth held frame paces it down to
# something that tracks more like a deliberate scroll-wheel turn. Raise
# for slower/gentler scrolling, lower (minimum 1) for faster.
SCROLL_FRAME_INTERVAL = 3


MOUSE_X_SENS = 1.0
MOUSE_Y_SENS = 2.0

# Fraction of the remaining distance to the target the cursor closes
# each frame (exponential smoothing). 0.1 was very sluggish -- at ~30fps
# it took roughly 20+ frames (~0.7s) to close 90% of the gap, which is
# why it felt like it needed repeated swipes to move any real distance.
# Raised to track much closer to the fingertip (like the debug dot)
# while still smoothing out a bit of frame-to-frame hand-tracking jitter.
MOUSE_SPEED = 0.65

# Cursor speed is scaled by this while the zoom gesture has the screen
# zoomed in. A fixed-size hand movement covers much more of the visible
# (zoomed-in) area than it would at normal zoom, so the same movement
# needs to move the cursor less on screen to still land precisely --
# without this, zooming in to make a small target easier to hit would
# make the now-larger target *harder* to land on, since the cursor would
# fly across it just as fast as before.
ZOOMED_MOUSE_SPEED_FACTOR = 0.5


# How confident the hand-landmark model must be before it'll report a
# hand/keep tracking it at all. Tuned for bare hands; a gloved hand (matte
# fabric/nitrile texture, no visible knuckle creases or nail/skin contrast)
# is a harder detection for a model trained mostly on bare-hand images, so
# it may need these lowered -- try 0.5/0.4 first if tracking drops out or
# never starts with gloves on. Lowering them trades some false-positive/
# jittery-tracking risk for a better chance of detecting the hand at all;
# there's no setting here that gets around the model's underlying
# training data (see the "Using this with gloves on" section of README.md).
MIN_DETECTION_CONFIDENCE = 0.7
MIN_TRACKING_CONFIDENCE = 0.5


# --- Hand-to-camera distance hint -----------------------------------------
#
# Every gesture cutoff above (FINGER_OUT_CUTOFF, LEFT_CLICK_CUTOFF, ...) is
# a raw camera-frame *pixel* distance, which means it implicitly assumes
# your hand is roughly a certain size on screen -- i.e. a certain distance
# from the camera. Too close and your hand fills more of the frame than
# that assumes (pinches read as "not quite together" even when your
# fingers are touching); too far and it fills less (folded fingers can
# still clear FINGER_OUT_CUTOFF, or a pinch never quite reads as closed).
# That's the "optimal distance" effect: it's not you, it's these pixel
# cutoffs being tuned for one specific hand size on screen.
#
# HAND_SCALE_REFERENCE below is that assumed hand size, measured as the
# wrist-to-middle-knuckle pixel distance (landmarks 0 and 9 -- a distance
# that stays roughly constant across hand poses, unlike fingertip-based
# measurements, so it's a stable stand-in for "how big does my hand look
# right now"). The overlay's control bar divides your hand's *live*
# wrist-to-middle-knuckle distance by this reference and shows "Move
# closer" / "Move back" / a normal (uncolored) status when you're outside
# a comfortable band around it -- see main_fast.py and overlay.py.
#
# This can't be pre-tuned for your camera/hand/desk setup the way the
# other cutoffs are documented as needing -- run with --debug once, hold
# your hand where clicks/poses register reliably, and note the
# "Hand scale: NNN" debug line; set HAND_SCALE_REFERENCE to that value.
# The default below is a rough placeholder, not a calibrated value.
HAND_SCALE_REFERENCE = 150

# Ratios (live hand_scale / HAND_SCALE_REFERENCE) outside this range show
# "Move back" (too close, hand looks larger than the reference) or "Move
# closer" (too far, hand looks smaller) on the control bar. Widened a bit
# past 1.0 on both sides so the hint doesn't flicker for ordinary
# in-and-out hand jitter -- tighten if you want earlier warning, widen if
# it fires too eagerly.
HAND_SCALE_TOO_CLOSE_RATIO = 1.3
HAND_SCALE_TOO_FAR_RATIO = 0.7


# Which hand does what (see main_fast.py) is decided strictly by hand
# identity -- right hand mouses/types, left hand zooms/pastes -- using
# MediaPipe's own per-hand Left/Right handedness label, whether one or
# both hands are visible (trying to reimplement that classification from
# raw finger geometry instead of trusting the model was tried and came
# out less reliable, not more). If mouse control and zoom ever come out
# swapped for your camera setup (e.g. you have to raise your *right*
# hand to zoom while your left hand drives the mouse), flip this rather
# than digging into main_fast.py -- it swaps the label for every
# detected hand, every frame.
SWAP_LABELED_HANDS = True