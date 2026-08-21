

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