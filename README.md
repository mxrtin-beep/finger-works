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

The left hand is dedicated to zoom and paste, so the right hand isn't
stuck doing everything. Which hand is which is decided by hand shape
(thumb vs. pinky position), not by which hand you're used to using for
mousing -- see "Which hand is which" below if it's ever backwards for
your setup.

- Thumb + index extended, then spread them apart: zoom in. Bring them
  back together: zoom out.

  This drives the OS's own screen magnifier (Windows Magnifier / macOS
  Zoom) rather than an in-app zoom, so it zooms *whatever's on screen* --
  a menu bar, a dialog, small toolbar icons -- not just apps that
  implement their own zoom. For it to zoom in around wherever your
  cursor currently is (rather than the whole screen), set it to "Lens"
  view once: Windows Settings > Accessibility > Magnifier > Views ->
  Lens; macOS System Settings > Accessibility > Zoom > Zoom Style ->
  Zoom Style: Lens. On Linux this instead falls back to Ctrl+Scroll,
  since screen-magnifier shortcuts vary a lot by desktop environment.

  This gesture only reacts once the pose has been held for a couple
  frames and thumb-index distance has clearly changed, so an idle left
  hand held still doesn't start zooming by accident -- but since only
  your left hand can trigger it at all now, it doesn't need to be as
  strict as an ordinary "any hand, any pose" gesture would. If it's
  still too easy (or too hard) to trigger, the thresholds are in
  `event_classifier.py` (`_ZOOM_ARM_FRAMES`, `_ZOOM_TRIGGER_DELTA`,
  `_ZOOM_TICK_COOLDOWN`).

- Pinky extended alone, other four fingers folded: paste (shortcut for
  the keyboard's 'Paste' key, without needing the keyboard open at all).

### Which hand is which

Left vs. right hand is worked out from finger geometry each frame (which
side of the wrist the thumb sits relative to the pinky) instead of trusting
MediaPipe's own handedness label, which turned out to flip unpredictably
across camera/mirroring setups. The overlay panel shows which hand(s) it
currently sees in brackets next to the action text (e.g. `Mousing
[Right]`) -- use that to check it's classifying your hands the way you'd
expect. If zoom/paste and mouse control ever come out swapped (e.g. you
have to raise your *right* hand to zoom), flip `MIRROR_HANDEDNESS_ORDER`
in `constants.py` rather than digging into the classifier itself.

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
