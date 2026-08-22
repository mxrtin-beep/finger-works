# FingerWorks -- Gestures & Parameters

A reference for every gesture the program recognizes and every tunable
parameter in `constants.py`. See `README.md` for setup/running instructions
and more narrative detail; this file is meant as a flat lookup.

## Running

    python main_fast.py [--sensitivity MULTIPLIER] [--debug]

- `--sensitivity MULTIPLIER` -- mouse-speed multiplier. Default `1.0`
  (today's normal speed, unchanged). `1.5` moves the cursor faster, `0.5`
  slower. A multiplier on top of `constants.MOUSE_SPEED`.
- `--debug` -- off by default. See "Debug mode" below.

## Debug mode

Off by default:

- The overlay panel (bottom-right corner of the screen) is **hidden**
  unless the on-screen keyboard is toggled on. It only appears when you
  actually need it -- to see and aim at the keyboard's keys -- and stays
  out of the way otherwise.
- No debug text is drawn, even while the keyboard is showing. You only see
  the keyboard itself and the typed-text preview line.

With `--debug`:

- The overlay panel is **always visible**, in both Mouse and Keyboard mode.
- The debug text is drawn at the top of the panel: the current event
  (`Mousing`, `Left-Click`, ...), the active control state (`Mouse` or
  `Keyboard`), and -- next to the action text -- which detected hand is
  doing what, e.g. `Mousing  [Right [Mouse]]`, or with a left hand also in
  frame, `Mousing  [Right [Mouse], Left [Zoom: open, normal] [Paste:
  neither (none out)]]`.
  - The `Right [...]` bracket shows which hand is driving the mouse/
    keyboard, or `Right [ignored]` if a second hand also read as "Right".
  - The `Left [Zoom: ...]` bracket shows the zoom gesture's live pose
    (`open`/`fist`/`neither (<fingers> out)`) and whether the screen is
    currently zoomed in (`zoomed`/`normal`); `-> sent zoom-in` / `-> sent
    zoom-out` is appended the instant a zoom action actually fires.
  - The `Left [Paste: ...]` bracket shows the paste gesture's live pose
    (`scissors`/`neither (<fingers> out)`); `-> sent paste` is appended the
    instant paste actually fires.
  - This is meant to answer "why isn't X working" directly: if a pose
    never reads as expected, detection isn't recognizing it (check
    lighting/framing, or `FINGER_OUT_CUTOFF`); if the pose registers but
    the action still doesn't happen, the gesture is fine and the problem
    is downstream (OS hotkey, focused app, etc.).

## Gestures

### Right hand -- mouse & keyboard

The right hand always drives the real OS cursor and (when toggled on) the
on-screen keyboard.

| Gesture | Action |
|---|---|
| Move hand | Moves the cursor, tracking your middle fingertip. |
| Pinch thumb + index | Left click. Keep it pinched while moving your hand to drag; release quickly for a plain click -- same gesture, distinguished only by how long you hold it, like a real mouse button. |
| Pinch thumb + ring | Right click. |
| Closed fist (no fingers extended) | Toggle the on-screen keyboard on/off. Edge-triggered on the fist *starting* -- holding it does nothing further until you release and re-form it. |
| Index + middle extended, others folded ("scissors") | **Keyboard mode only:** cut the keyboard's own typed-text buffer (shortcut for the on-screen `Cut Typed` key). In Mouse mode this pose just does nothing (treated as an ordinary hand pose). |
| Thumb + pinky extended, other three folded | Quit the program. |

While the keyboard is open, clicking still works normally as long as the
cursor isn't currently over one of the keyboard's own buttons -- so you can
type something, then click elsewhere (e.g. confirm a rename, or click into
another field) without closing the keyboard first.

### Left hand -- zoom & paste

The left hand is dedicated to zoom and paste, so the right hand isn't stuck
doing everything. Routing is strict, by hand identity (MediaPipe's own
Left/Right classification of each detected hand, independent of whether the
other hand is also in frame) -- showing only your left hand never falls
back to mouse control.

| Gesture | Action |
|---|---|
| Open hand, all five fingers extended | Zoom in (drives the OS's own screen magnifier). Does nothing if already zoomed in. |
| Closed fist | Zoom back out. Does nothing if not currently zoomed in. |
| Index + middle extended, others folded ("scissors") | Paste -- shortcut for the on-screen keyboard's `Paste` key, without needing the keyboard open at all. Reads the OS clipboard and types its contents as real keystrokes. |

Zoom holds a single on/off level, not a repeatable "tick": forming the
zoom-in pose while already zoomed in does nothing (close to a fist first),
and a fist does nothing unless you're currently zoomed in. That's what
keeps one continuous pose from stacking up several zoom steps at once. Zoom
is also automatically restored to normal when the program quits while still
zoomed in, so it doesn't leave your screen zoomed in behind it.

Cursor speed is automatically halved while zoomed in (`ZOOMED_MOUSE_SPEED_FACTOR`,
see below), and restored the moment you zoom back out.

For the OS-level zoom hotkey used per platform (Windows Magnifier,
macOS Zoom, Linux Ctrl+Scroll fallback) and how to set "Lens" view so zoom
follows your cursor, see `README.md`.

### On-screen keyboard keys

Once the keyboard is toggled on (right-hand fist), these are the
utility keys in its bottom row, beyond the regular QWERTY letters/digits:

| Key | Action |
|---|---|
| `Space` | Types a space. |
| `<` | Backspace. |
| `Clear` | Clears this keyboard's own typed-text preview line only (not anything on your desktop). |
| `Copy` | Sends a real Ctrl+C -- copies whatever's currently selected elsewhere on your desktop. |
| `Cut` | Sends a real Ctrl+X. |
| `Copy Typed` | Copies this keyboard's own typed-text buffer (the preview line, not your desktop selection) to the OS clipboard. |
| `Cut Typed` | Same, then clears the preview line. Also reachable via the right-hand "scissors" gesture. |
| `Paste` | Reads the OS clipboard and types its contents as real keystrokes. Also reachable via the left-hand "scissors" gesture, without opening the keyboard. |

## Parameters (`constants.py`)

| Parameter | Meaning |
|---|---|
| `FINGER_OUT_CUTOFF` | Wrist-relative pixel distance above which a fingertip counts as "extended" rather than folded. Drives every pose gesture (fist, scissors, zoom's open-hand/fist). Raise if poses aren't registering as extended when they should; lower if folded fingers are misread as extended. |
| `LEFT_CLICK_CUTOFF` | Max thumb-to-index pixel distance that counts as a left-click pinch. Higher = a lighter tap triggers a click; too high risks false clicks from your hand's normal resting/aiming pose. |
| `RIGHT_CLICK_CUTOFF` | Same, for thumb-to-ring (right-click pinch). |
| `SCROLL_VEL_CUTOFF` | (Reserved for scroll-gesture velocity threshold.) |
| `MOUSE_X_SENS` / `MOUSE_Y_SENS` | Per-axis scale applied when mapping the fingertip's position in the camera frame onto screen coordinates. |
| `MOUSE_SPEED` | Fraction of the remaining distance to the target the cursor closes each frame (exponential smoothing). Higher tracks the fingertip more tightly; lower is smoother but laggier. Also scaled by `--sensitivity` at runtime. |
| `ZOOMED_MOUSE_SPEED_FACTOR` | Multiplies `MOUSE_SPEED` while the zoom gesture has the screen zoomed in, since the same hand movement then covers much more of the visible area. |
| `MIN_DETECTION_CONFIDENCE` / `MIN_TRACKING_CONFIDENCE` | How confident MediaPipe's hand-landmark model must be before it reports/keeps tracking a hand. Lower (e.g. 0.5/0.4) if tracking drops out with gloves on; trades some false-positive/jitter risk for better detection. See "Using this with gloves on" in `README.md`. |
| `SWAP_LABELED_HANDS` | Flips MediaPipe's Left/Right hand label for every detected hand, every frame. Set if mouse/keyboard control and zoom/paste ever come out swapped for your camera setup (e.g. your right hand ends up zooming instead of mousing). |
