# finger-works

A program to allow you to control your computer without touching it. It uses your webcam to track your finger movements and pick up commands.

## License

All rights reserved -- see `LICENSE`. This is proprietary; using, copying,
or redistributing it requires the copyright holder's permission. (Its
open-source dependencies -- OpenCV, MediaPipe, NumPy, PyAutoGUI,
PyPerClip -- keep their own separate licenses.)

## Running it

    python main_fast.py [--sensitivity MULTIPLIER] [--debug]

`--sensitivity` scales overall cursor speed. It defaults to `1.0` (the
program's normal speed, unchanged); `1.5` moves the cursor faster, `0.5`
slower. It's a multiplier on top of `constants.MOUSE_SPEED`, so you don't
need to edit that file just to try a faster or slower feel.

`--debug` is off by default. Without it, the overlay panel stays hidden
except while the on-screen keyboard is toggled on, and no debug text is
drawn. With it, the panel is always visible and shows the debug text
(current event, mouse sensitivity, which hand is doing what, live
zoom/paste gesture state), and a second window shows the live camera feed
with each hand's skeleton traced and its current gesture labeled in real
time -- see `INSTRUCTIONS.md` for the full rundown of gestures, parameters,
and what the debug output means.

A small control bar always sits in the bottom-right corner of the screen
with **Pause**/**Resume**, **Help**, **Settings**, and **Quit** -- so you
can pause tracking, look up the gestures, change your camera/sensitivity/
debug mode, or quit, without needing a gesture or the command line. Camera
picking defaults to auto (the first camera that opens, same as always),
overridable in Settings if you have more than one webcam. By default the
on-screen keyboard types into whatever text box/app is actually focused,
like a physical keyboard -- Settings also has a checkbox to switch it back
to typing into the keyboard's own preview line instead (move it elsewhere
yourself with `Copy Typed`/`Cut Typed`), if you'd rather have that.
Settings persist across restarts (`~/.finger_works_settings.json`); see
`INSTRUCTIONS.md` for details.

The on-screen keyboard is laid out roughly like a physical/phone keyboard:
`Tab`, `Caps`, and a `Shift` down the left of the QWERTY block, `Enter`
and another `Shift` on the right, and a wide `Space` bar along the bottom.
`Shift` capitalizes just the next letter (like a phone keyboard); `Caps`
stays on until pressed again. Actions with no physical-keyboard spot of
their own -- `Undo`/`Redo`, `Select All`, clipboard keys, and a `123`/`ABC`
key that switches the letter rows to a symbols page (common punctuation
and math symbols) and back -- sit in their own row under `Space`. The
digit row on top stays put on both pages.

Clicking the keyboard panel's own gray background (between keys, not on
any of them) does nothing at all now, rather than passing through as a
real click on whatever's visually behind the panel -- that stray click was
the main remaining way typing could lose focus on the text box you were
using, separate from the "focus follows mouse" issue below.

On window managers with "focus follows mouse", aiming the cursor at the
next on-screen key can otherwise silently steal keyboard focus away from
the text box you were typing into. Typing now remembers the last real
window you clicked into and force-restores it to the foreground (via
Windows' AttachThreadInput trick, since a plain focus-switch request is
usually blocked by Windows' own anti-focus-stealing protection) right
before every keystroke. Windows only for now -- if you're on macOS/Linux
and still see this, let us know.

The Windows focus-restore code also had a real bug of its own: the raw
ctypes calls it made weren't given explicit argument/return types, which
lets ctypes silently truncate window handles (64-bit pointers) down to
32 bits -- occasionally targeting the wrong window entirely. Fixed by
declaring proper types for every WinAPI call involved.

Every frame is now wrapped in its own error handler: an unexpected hiccup
(camera, model, or an OS call having a bad moment) gets logged and skips
to the next frame instead of crashing the whole program. Previously, a
crash meant an unhandled Python traceback got printed straight to this
program's console window -- and since it drives the real mouse and does
real clicks, that traceback text could plausibly end up selected/copied
from the console (e.g. via Windows console "QuickEdit" text selection)
and later typed out somewhere else entirely by a stray `Paste`, which is
likely what caused occasional "Traceback" text showing up in other apps.

Startup now opens the camera and loads the hand-tracking model at the same
time instead of one after the other, and prints how long each step took --
if startup still feels slow, those two timings (and how long it took
`ensure_model_downloaded()` to run, on a first run before the model file
exists locally) point to which part to look at next.

The control bar, its margins, and the debug camera window are all sized as
a fraction of your screen resolution (clamped to a sane min/max) rather
than fixed pixel counts, so they look proportionally similar on a small
laptop screen and a large or 4K monitor instead of tiny on one and
oversized on the other.

Cursor speed is also automatically halved while the zoom gesture has the
screen zoomed in, and restored the moment you zoom back out (or if the
program quits while still zoomed in) -- a given hand movement covers much
more of the now-magnified view, so it needs to move the cursor less on
screen to still land precisely on a small target. `--sensitivity` still
applies underneath that: it changes your overall baseline speed, zoomed
or not.

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
- Thumb + pinky extended, others folded: pause (use the control bar's
  Quit button, or Escape, to actually quit).

While the keyboard is open, clicking still works normally as long as the
cursor isn't over one of the keyboard's own buttons -- so you can type a
name, then click elsewhere (e.g. to confirm a rename, or click into
another text field) without having to close the keyboard first.

The left hand is dedicated to zoom and paste, so the right hand isn't
stuck doing everything. This is strict, by hand identity, whether or not
your other hand is in frame at all -- if you raise only your left hand,
it will only ever zoom/paste, never mouse (see "Which hand does what"
below):

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

  On Windows, if you hear a system "ding" instead of seeing it zoom,
  that's Windows itself telling you the shortcut is disabled -- check
  Settings > Accessibility > Magnifier > "Allow the shortcut key to
  start this feature".

  Zoom only ever holds a single level, on or off -- forming the
  zoom-in pose while already zoomed in does nothing (close to a fist
  first), and a fist does nothing unless you're currently zoomed in.
  That's what keeps one gesture from stacking up several zoom steps at
  once (it fires the instant it sees the pose, with no held-for-a-moment
  delay), and it also zooms back out automatically when you quit the
  program, so it doesn't leave your screen zoomed in behind it. If a
  quick incidental flash of open-hand/fist ever ends up triggering zoom
  by accident, `_ZOOM_ARM_FRAMES` in `event_classifier.py` adds back a
  hold delay.

- Index + middle extended ("scissors") -- the same shape as the right
  hand's Cut-Typed gesture, but paste on this hand: a shortcut for the
  keyboard's 'Paste' key without needing the keyboard open at all.

### Which hand does what

Every detected hand is independently classified Left or Right by
MediaPipe (this doesn't depend on whether a second hand is also in
frame), and routed strictly by that: right hand mouses/types, left hand
zooms/pastes, always -- regardless of whether one or both hands are
visible. Showing only your left hand does not fall back to mouse
control; it does zoom/paste or nothing.

The overlay panel shows the resolved role next to each detected hand's
label in brackets next to the action text (e.g. `Mousing  [Right
[Mouse]]`). If it ever comes out backwards for your camera setup -- your
left hand mousing instead of your right -- flip `SWAP_LABELED_HANDS` in
`constants.py`; it swaps the label for every detected hand, every frame.

For the left/zoom hand specifically, the bracket also shows *live*
detection state instead of just the static "Zoom" role, e.g.
`Left [Zoom: open, normal]` -- which pose it's currently reading
(`open`/`fist`/`neither`, plus which fingers it saw as extended if
neither matched), and whether the screen is currently zoomed in or at
normal. When a zoom action actually fires, `-> sent zoom-in` or `-> sent
zoom-out` is appended. This is meant to answer "why isn't zoom working"
directly: if the pose never reads as `open`/`fist` when you form it,
detection itself isn't recognizing it (check lighting/framing, or that
`FINGER_OUT_CUTOFF` fits your hand/camera); if it does and still doesn't
zoom, the gesture is fine and the problem is downstream, in the OS
hotkey `execute_zoom()` sends (e.g. the OS magnifier isn't installed/
enabled, or another app is capturing that shortcut).

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
