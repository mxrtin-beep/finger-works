# 🖐️ FingerWorks

Control your computer using hand gestures recognized by your webcam --
no touching required. Or put the same hand tracking to creative use:
**paint** on a canvas in the air, or **play music** with nothing but your
hands (see [Modes](#modes)).

## License

All rights reserved -- see `LICENSE`. This is proprietary; using, copying,
or redistributing it requires the copyright holder's permission. (Its
open-source dependencies -- OpenCV, MediaPipe, NumPy, PyAutoGUI,
PyPerClip -- keep their own separate licenses.)

## Getting Started

**Windows:** download and run `FingerWorks.exe` from the
[latest release](https://github.com/mxrtin-beep/finger-works/releases/latest) --
no Python install needed.

**From source:**

    python main_fast.py [--sensitivity MULTIPLIER] [--mode control|paint|music] [--debug]

A small control bar (**Pause**, **Mode**, **Help**, **Settings**, **Quit**)
sits in the bottom-right corner of the screen at all times, so you can
pause tracking, switch modes, look up the gestures, or quit without
needing a gesture or the command line. Minimize the console once it's running.

Demo: https://www.youtube.com/watch?v=EUsH5B4Lh8c&feature=youtu.be

## Basic Gestures

**Right hand**
- ✋ Move your hand → moves the cursor (follows middle finger)
- 🤏 Pinch thumb + index → left click (hold to drag)
- 🤏 Pinch thumb + ring → right click
- ✊ Closed fist → toggle the on-screen keyboard
- 🤙 Hang Ten sign (thumb and pinky out) → pause

**Left hand**
- ✋ Open palm → zoom in · ✊ Fist → zoom out
- ☝️ Index finger pointing up → scroll up
- 👎 Thumb pointing down → scroll down

Click **Help** in the control bar any time for the full gesture list, or
see the [Gestures](#gestures) section below for the complete rundown.

## Modes

FingerWorks has three modes. The one you've always had -- **Control** --
is what it starts in. Switch with the control bar's **Mode** button (or
`--mode paint` / `--mode music` on the command line); it always starts in
Control mode next time, however you left it.

| Mode | What it does |
|---|---|
| **Control** | Your hands run the computer: cursor, clicks, on-screen keyboard, zoom, scroll. |
| **Paint** | Paint with living light: pinch to ignite, clench to gather, snap open to burst; tilt your left hand to tune. |
| **Music** | An instrument in the air: a harp you strum, keys you pinch, or a theremin you wave at. |

Both artistic modes have no keyboard, zoom or scroll, and they never touch
your real mouse -- the hands only drive the canvas. Your hand is mapped to
the screen generously (the middle ~55% of the camera's view covers all of
it), so you can sit back and keep your whole hand in frame. The 🤙 **Hang Ten**
sign (thumb and pinky out, on *either* hand, held for a moment) still
pauses; the control bar stays on top so you can switch mode, un-pause or
quit with your physical mouse.

### 🎨 Paint

Not a drawing tool -- a piece of living light. The screen is a field of
glowing motes drifting in an invisible flow, alive even with nobody in
front of it (leave it alone and a ghost painter takes over). Your hands act
on it, and everything leaves long-exposure trails.

**Right hand -- the conductor.** It aims where your **middle finger
points**, exactly like the cursor in Control mode.

- 🤏 Pinch thumb + index → **ignite**: pour light along your path
- ✊ Clench your fist → **gather**: the light is drawn into orbit and
  condenses into a blazing core
- 🖐️ Snap the fist open → **burst**: a shockwave of light rings outward
- Just moving stirs the field, and every fingertip sheds sparks

**Left hand -- the atmosphere.** Hold a pose, then **tilt your hand like a
joystick**: lean right to keep raising a value, lean left to keep lowering
it, straighten up to hold it. There's no range limit -- it can go as far as
you like -- and a small wrist movement is enough.

| Pose | Tilting changes |
|---|---|
| ☝️ One finger | **Colour** -- rotates everything through the palette |
| ✌️ Two fingers | **Glow** -- thin sparks ↔ fat halos |
| Three fingers | **Flow** -- calm ↔ turbulent |
| 🖐️ Four fingers / open hand | **Trails** -- short sparks ↔ long exposure |
| ✊ Fist, held | **Stops time** -- everything hangs in the air; open to resume |
| 👍 Thumb alone, held | Next **palette** (Aurora, Ember, Ocean, Nebula, Prism) |

The control bar gains **Palette**, **Reset** and **Save** buttons (Save
writes a full-resolution PNG to `Pictures/FingerWorks` -- handy for
stills).

### 🎵 Music

Every note comes from the **key and scale** you pick in Settings (default
C major pentatonic), so there are no wrong notes.

**Left hand -- harmony and dynamics.**

- Hold up **1 · 2 · 3 · 4 fingers** → chord **I · IV · V · vi** (in a
  minor scale: **i · iv · VI · VII**). The chord stays until you pick
  another.
- Hand **height** is the volume: raise it to swell, lower it to soften.
- A soft **chord pad** plays underneath whatever instrument you're on, so a
  chord change is always audible -- including on Keys, whose notes are
  scale notes and so don't depend on the chord.
- 👍 Thumb alone, held a moment → next instrument.

**Right hand -- the instrument** (the control bar's **Mode** window or
**Next instrument** button also switch between them):

- **Harp** -- a compact harp in the top half of the screen: sweep your
  **index finger** across ten strings to strum. They're tuned to the
  current chord, and plucks pan left-to-right with the string.
- **Keys** -- pinch thumb + index over a key to play it; slide while
  pinched for a glissando. Keys that belong to the current chord are lit.
- **Theremin** -- hand left/right is pitch (gently pulled toward the
  scale), hand height is vibrato, a fist is silence.

Sound needs `pygame` (optional for the rest of FingerWorks). Without it
the visuals still run and the window says so. Install it with
`pip install pygame`, **or `pip install pygame-ce` if that fails** -- on
newer Pythons (3.14 at the time of writing) plain `pygame` has no
prebuilt Windows wheel and tries to compile from source, which usually
errors out. `pygame-ce` is a maintained drop-in fork with prebuilt wheels;
it's still imported as `pygame`. Install one or the other, not both. All sounds are synthesized -- there are
no audio files to ship.

See `INSTRUCTIONS.md` for the complete reference.

## 🐞 Debug Mode

Off by default. Turn it on in **Settings** (or run with `--debug`) to see
a live camera feed with your hand tracking overlaid, plus diagnostic text
(current event, mouse sensitivity, which hand is doing what, live
zoom/paste gesture state) -- see `INSTRUCTIONS.md` for the full rundown of
gestures, parameters, and what the debug output means.

If you're running a packaged `.exe` build (Windows) rather than
`python main_fast.py` directly, its console window is hidden the same way
by default (no debug text there either), and reappears automatically the
moment debug mode is turned on -- either at startup (`--debug`) or live
from the Settings window's debug checkbox. This applies no matter how the
exe was launched, including from an already-open PowerShell/cmd window --
so testing it from a terminal without `--debug` will hide that window too,
not just a double-clicked one; pass `--debug` (or turn it on in Settings)
to keep it visible while you're working with it that way. If FingerWorks
fails to start at all, its console is always shown regardless of debug
mode, with the error printed there and the window kept open until you
press Enter -- so a startup failure is never silent, just because debug
mode happened to be off.

A small control bar always sits in the bottom-right corner of the screen
with **Pause**/**Resume**, **Help**, **Settings**, and **Quit** -- so you
can pause tracking, look up the gestures, or quit, without needing a
gesture or the command line. Both it and the keyboard/debug panel above
it are movable: pinch-and-hold-and-drag the control bar's `⋮⋮` grip, or
the keyboard panel's `⋮⋮⋮⋮⋮⋮` strip along its top, to reposition either
one wherever's convenient -- neither remembers a moved position across
restarts, both are always back at their default spot next launch.
**Settings** covers camera, debug mode, four
feel-tuning sliders (mouse sensitivity, cursor snappiness -- see "Does the
cursor feel like it's sliding?" below -- scroll speed, and on-screen
keyboard size), and two off-by-default sound toggles (a short, quiet tone on
clicks and/or keyboard presses -- deliberately light, not an obvious
"beep"). A **Reset to Defaults** button in Settings puts every field back to
its shipped default (Apply afterward to actually use them). The on-screen
keyboard always types into whatever text box/app is actually focused,
like a physical keyboard. Settings persist across restarts
(`~/.finger_works_settings.json`) -- except debug mode, which is always
back off the next time you start the program, however you left it; see
`INSTRUCTIONS.md` for details.

### Does the cursor feel like it's sliding?

There are two separate smoothing layers between your fingertip and the
cursor: one damps small (likely-jitter) movements before the cursor even
starts moving toward them, the other governs how fast the cursor then
closes in on wherever it's currently aiming. Historically only the second
was adjustable (`--sensitivity`, or the sensitivity slider). If the cursor
tracks large movements fine but feels laggy/floaty on small, precise ones,
that's almost always the first layer -- raise **Cursor snappiness** in
Settings. Higher trades some visible raw hand-tracking jitter for a
cursor that responds to small movements almost immediately; lower trades
the reverse.

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
- Point up (index finger extended and aimed upward, other four folded):
  scroll up. Thumb down (thumb extended and aimed downward, other four
  folded -- a "thumbs down"): scroll down. Different fingers rather than
  the same pose flipped upside down, since pointing the index finger
  downward turned out to be an easy pose for zoom's open-hand gesture to
  misfire on (see `event_classifier.py`'s scroll-gesture comment for why).
  Keep either pose held to keep scrolling; it's sent in small ticks every
  frame rather than infrequent big jumps, tuned to add up to the same
  overall speed either way -- see the Settings "Scroll speed" slider, or
  `SCROLL_AMOUNT`/`SCROLL_FRAME_INTERVAL` in `constants.py`.

### Does my hand distance from the camera matter?

No, by design: every gesture cutoff (pinch distance, finger-extended
distance) is compared against your hand's own live size in the camera
frame (its wrist-to-middle-knuckle pixel distance), not a fixed pixel
count. A hand that's closer to the camera has both a bigger raw fingertip
distance *and* a bigger reference size, so the ratio between them --
what's actually compared to the cutoff -- stays the same. There's no
"sweet spot" distance to find; move closer or farther and clicks/poses
should keep registering the same way. See the "Distance-independent
gesture cutoffs" comment at the top of `constants.py` for the full
explanation, and `mouse_control.normalize_landmarks()` for where it
happens.

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

## Tests

    python -m unittest discover -s tests -t .

Covers the gesture helpers, music theory, the light engine and the synth.
(`settings` tests need OpenCV installed, and the audio-engine test needs
`pygame`; each is skipped or degrades gracefully if missing.)

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
