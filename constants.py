

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