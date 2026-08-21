

THUMB_IDX = 4
INDEX_IDX = 8
MIDDLE_IDX = 12
RING_IDX = 16
PINKY_IDX = 20

FINGER_NAMES = ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']
FINGER_INDICES = [4, 8, 12, 16, 20]
#FINGER_OUT_CUTOFF = 2.5e4

FINGER_OUT_CUTOFF = 280


LEFT_CLICK_CUTOFF = 50
RIGHT_CLICK_CUTOFF = 50

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