

THUMB_IDX = 4
INDEX_IDX = 8
MIDDLE_IDX = 12
RING_IDX = 16
PINKY_IDX = 20

FINGER_NAMES = ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']
FINGER_INDICES = [4, 8, 12, 16, 20]

# --- Distance-independent gesture cutoffs ---------------------------------
#
# Every cutoff below (FINGER_OUT_CUTOFF, LEFT_CLICK_CUTOFF,
# RIGHT_CLICK_CUTOFF) used to be a raw camera-frame *pixel* distance, which
# implicitly assumed your hand was a certain size on screen -- i.e. a
# certain distance from the camera. That's what caused the "optimal
# distance" effect: too close and a pinch could read as "not quite
# together" even with fingers touching; too far and folded fingers could
# still clear the extended-finger cutoff.
#
# Fix: every landmark position gesture detection looks at is first divided
# by the hand's own live wrist-to-middle-knuckle pixel distance (landmarks
# 0 and 9; stable across hand poses, unlike a fingertip-based measurement,
# see mouse_control.hand_scale()) -- before being compared to a cutoff. A
# bigger hand on screen (closer to the camera) has both a bigger raw
# fingertip distance *and* a bigger live hand-scale, so the ratio between
# them stays the same regardless of distance. The cutoffs below are
# therefore unitless ratios, not pixel counts, and (in principle) don't
# need retuning if you sit closer/farther from the camera, or if someone
# else with different-sized hands uses this. See mouse_control.hand_scale()
# and main_fast.py, where every hand's landmarks are normalized by it once
# per frame, before any gesture is read off them.
#
# HAND_SCALE_TUNING_REFERENCE is the wrist-to-middle-knuckle pixel distance
# each ratio below is calibrated against: cutoff_ratio = old_pixel_cutoff /
# HAND_SCALE_TUNING_REFERENCE. Getting this one number right is what makes
# the *feel* of clicking/posing match the old pixel-tuned cutoffs; getting
# it wrong shifts every cutoff by the same wrong factor at once, which
# reads as gestures generally misbehaving (fingers popping "extended" too
# easily and breaking fist detection, or the reverse) even right back at
# the distance that always used to work. If that happens: run with
# --debug, hold your hand exactly where clicks/poses used to register
# reliably, read the "scale=NNN" value shown next to `Right [Mouse` in the
# debug text/overlay, and set this to that number -- every ratio below
# rescales together, so this is the one thing to retune, not each cutoff
# individually.
HAND_SCALE_TUNING_REFERENCE = 150

FINGER_OUT_CUTOFF = 280 / HAND_SCALE_TUNING_REFERENCE   # extended-finger cutoff, was 280px

# Max thumb-to-fingertip distance (relative to hand size) that counts as a
# pinch/click. Was raised from 50px to 70px -- at 50, registering a click
# required pressing the thumb and index almost fully together, hard enough
# that it dragged the rest of the hand (including the middle finger, which
# aims the cursor) along with it. Higher = lighter tap triggers a click,
# but too high risks false clicks from your hand's normal resting pose
# while just aiming/hovering. This is a fine line and worth retuning for
# your own hand/camera setup if it still feels off in either direction.
LEFT_CLICK_CUTOFF = 70 / HAND_SCALE_TUNING_REFERENCE    # was 70px
RIGHT_CLICK_CUTOFF = 60 / HAND_SCALE_TUNING_REFERENCE   # was 60px

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
SCROLL_AMOUNT = 80

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