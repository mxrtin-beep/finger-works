# finger-works

A program to allow you to control your computer without touching it. It uses your webcam to track your finger movements and pick up commands.

## License

All rights reserved -- see `LICENSE`. This is proprietary; using, copying,
or redistributing it requires the copyright holder's permission. (Its
open-source dependencies -- OpenCV, MediaPipe, NumPy, PyAutoGUI,
PyPerClip -- keep their own separate licenses.)

## Gestures

The right hand drives the mouse and (optionally) the keyboard:

- Move your hand: moves the cursor.
- Pinch thumb + index: left click. Keep it pinched while moving your hand
  to drag; release quickly for a plain click -- it's the same gesture,
  distinguished only by how long you hold it, like a real mouse button.
- Pinch thumb + ring: right click.
- Closed fist: toggle the on-screen keyboard on/off.
- Index + middle extended ("scissors"): cut the keyboard's typed-text
  buffer (shortcut for the 'Cut Typed' key).
- Thumb + pinky extended, others folded: quit.

While the keyboard is open, clicking still works normally as long as the
cursor isn't over one of the keyboard's own buttons -- so you can type a
name, then click elsewhere (e.g. to confirm a rename, or click into
another text field) without having to close the keyboard first.

A second hand, when it's raised alongside your mouse hand, is dedicated
to zoom and paste, so the right hand isn't stuck doing everything:

- Open hand, all five fingers extended: zoom in. Closed fist: zoom back
  out. Deliberately simple, maximally-different poses so detection
  itself is reliable -- these two are about as far apart in "fingers
  out" terms as two poses can be.

  This drives the OS's own screen magnifier (Windows Magnifier / macOS
  Zoom) rather than an in-app zoom, so it zooms *whatever's on screen* --
  a menu bar, a dialog, small toolbar icons -- not just apps that
  implement their own zoom. For it to zoom in around wherever your
  cursor currently is (rather than the whole screen), set it to "Lens"
  view once: Windows Settings > Accessibility > Magnifier > Views ->
  Lens; macOS System Settings > Accessibility > Zoom > Zoom Style ->
  Zoom Style: Lens. On Linux this instead falls back to Ctrl+Scroll,
  since screen-magnifier shortcuts vary a lot by desktop environment.

  Zoom only ever holds a single level, on or off -- forming the
  zoom-in pose while already zoomed in does nothing (close to a fist
  first), and a fist does nothing unless you're currently zoomed in.
  Each pose also has to be held for several consecutive frames before it
  fires. Together that's what keeps one gesture from stacking up several
  zoom steps at once, and it also zooms back out automatically when you
  quit the program, so it doesn't leave your screen zoomed in behind it.
  The hold-time is `_ZOOM_ARM_FRAMES` in `event_classifier.py` if it
  needs retuning.

- Index + middle extended ("scissors") -- the same shape as the right
  hand's Cut-Typed gesture, but paste on this hand: a shortcut for the
  keyboard's 'Paste' key without needing the keyboard open at all.

### Which hand does what

With only one hand visible, it's unconditionally the mouse/keyboard hand
-- zoom and paste need a second hand in frame to mean anything, so
there's no ambiguity to get wrong in the common case of mousing around
with just one hand up. With two hands visible, MediaPipe's own
Left/Right handedness label decides which does which (right hand mouses,
left hand zooms/pastes). The overlay panel shows the current assignment
in brackets next to the action text (e.g. `Mousing  [Mouse, Zoom]`) so
you can check it's routing your hands the way you expect. If it ever
comes out backwards for your camera setup, flip `SWAP_LABELED_HANDS` in
`constants.py`.

## Using this with gloves on

Hand tracking here is done by MediaPipe's HandLandmarker model, which (like
essentially every off-the-shelf hand-tracking model) is trained on bare
hands -- it's learned to find hands by recognizing skin tone, knuckle
creases, nail outlines, and finger silhouette, all of which a glove
partially or fully hides. That means:

- **A thin, snug, translucent glove** (the kind labs commonly use) has the
  best chance of working, since it distorts the hand's outline the least.
  Detection may still be less reliable than bare-handed, especially for
  the color-checking done by some vision pipelines -- this project's
  gesture detection is fully geometry/landmark-based (finger positions and
  distances), not color-based, so glove color (gray, purple, blue, green,
  etc.) shouldn't matter to it either way.
- **A loose, thick, or opaque glove** changes the hand's silhouette enough
  that the underlying model may lose tracking altogether, especially at
  the fingertips, where our gestures (pinch distance, extended/folded
  fingers) matter most.
- Lowering `MIN_DETECTION_CONFIDENCE` / `MIN_TRACKING_CONFIDENCE` in
  `constants.py` (try 0.5 / 0.4) can help the model hang on to a gloved
  hand it would otherwise drop, at the cost of occasional false detections
  or jitter -- worth trying first since it's a one-line change.
- Good, even lighting and a plain background behind your hand also help
  meaningfully, since they're what the model otherwise has to work hardest
  to see past.

None of the above is a real fix, though -- it's tuning an existing bare-hand
model, not adapting it to gloves. The actual fix is a hand-landmark model
fine-tuned (or trained from scratch) on labeled images of gloved hands in
the colors you actually use. That's realistic to do -- MediaPipe publishes
a "Model Maker" retraining pipeline for hand landmarks -- but it needs a
dataset (a few hundred to a few thousand labeled images per glove
color/lighting condition is a reasonable starting target) that doesn't
exist yet for this project. If glove support matters enough to invest in,
the practical path is: collect a small labeled dataset of gloved hands
(gray/purple/blue/green, your actual lab lighting) and fine-tune the
landmark model on it, rather than trying to configure our way there.
