# finger-works

A program to allow you to control your computer without touching it. It uses your webcam to track your finger movements and pick up commands.

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

The left hand is dedicated to zoom, so the right hand isn't stuck doing
everything:

- Thumb + index extended, other three fingers folded, then spread the
  thumb and index apart: zoom in. Bring them back together: zoom out.
  (Sends Ctrl+Scroll, which most zoomable apps -- image viewers, maps,
  design tools, browsers -- treat as a zoom.)

This gesture is intentionally picky about triggering: it only reacts once
the pose has been held for a few frames and only once thumb-index
distance has clearly changed, specifically so that resting your left hand
in roughly that shape doesn't accidentally start zooming. If it's still
too easy (or too hard) to trigger for your hand/camera setup, the
thresholds are in `event_classifier.py` (`_ZOOM_ARM_FRAMES`,
`_ZOOM_TRIGGER_DELTA`, `_ZOOM_TICK_COOLDOWN`).

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
