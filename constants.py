

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
# Measured directly (--debug's scale=NNN reading, at the distance
# gestures used to work reliably at): ~200-250, so 225 (the midpoint).
HAND_SCALE_TUNING_REFERENCE = 225

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

# Same idea for the thumb (its MCP joint, landmark 2) -- used by the
# scroll-down gesture (thumb extended and aimed down, other four folded)
# to read which way the thumb is pointing.
THUMB_MCP_IDX = 2

# How many pixels (in OS-scroll units, same as pyautogui.scroll()'s
# argument) one scroll "tick" moves while the point-up/point-down gesture
# is held. Applied every SCROLL_FRAME_INTERVAL-th frame -- see that
# constant just below for why SCROLL_AMOUNT and SCROLL_FRAME_INTERVAL are
# tuned as a pair, not independently.
SCROLL_AMOUNT = 27

# The point-up/point-down scroll gesture is held continuously (unlike the
# edge-triggered fist/scissors gestures). An earlier version sent a large
# SCROLL_AMOUNT (80) only every 3rd held frame -- meant to avoid a firehose
# of ticks, but the actual effect was the opposite of smooth: the page
# visibly jumped in big steps every 3rd frame instead of gliding, which is
# what "choppy" was describing. SCROLL_AMOUNT and SCROLL_FRAME_INTERVAL are
# now tuned together to keep the same *overall* scroll speed (amount /
# interval) while delivering it in smaller, more frequent ticks -- finer
# granularity reads as smooth scrolling, the same total distance delivered
# in fewer/bigger ticks reads as choppy. Retune as a pair (e.g. to change
# overall speed without changing smoothness, scale SCROLL_AMOUNT and use
# the Settings "Scroll speed" slider instead of touching this file) rather
# than raising/lowering just one of the two.
SCROLL_FRAME_INTERVAL = 1


MOUSE_X_SENS = 1.0
MOUSE_Y_SENS = 2.0

# Fraction of the remaining distance to the target the cursor closes
# each frame (exponential smoothing). 0.1 was very sluggish -- at ~30fps
# it took roughly 20+ frames (~0.7s) to close 90% of the gap, which is
# why it felt like it needed repeated swipes to move any real distance.
# Raised to track much closer to the fingertip (like the debug dot)
# while still smoothing out a bit of frame-to-frame hand-tracking jitter.
MOUSE_SPEED = 0.65

# Bounds for the Settings window's "Cursor snappiness" slider, which
# controls how heavily small (likely-jitter) fingertip movements get
# damped before the cursor even starts closing in on them -- see
# mouse_control._smooth_fingertip()/set_cursor_snappiness(). The slider
# runs 0.0 (max smoothing -- steadiest, but reads as "sliding"/laggy for
# small precise movements) to 1.0 (snappiest -- tracks your fingertip
# almost immediately, but shows more raw hand-tracking jitter), linearly
# interpolated between these two alpha values. This is a separate knob
# from MOUSE_SPEED/`--sensitivity` above: that one governs how fast the
# cursor closes the gap to an already-computed target position; this one
# governs how readily small movements even *move* that target position
# in the first place, which is what mainly reads as "sliding" when it's
# too heavily smoothed.
JITTER_ALPHA_MIN = 0.05
JITTER_ALPHA_MAX = 0.6

# Smoothing factor applied to larger, clearly-intentional fingertip
# movement -- always fast, regardless of the snappiness slider, since
# there's no jitter-vs-intent ambiguity to weigh once a movement is this
# big.
INTENT_ALPHA = 0.9

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