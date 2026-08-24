# FingerWorks -- Gestures & Parameters

A reference for every gesture the program recognizes and every tunable
parameter in `constants.py`. See `README.md` for setup/running instructions
and more narrative detail; this file is meant as a flat lookup.

## Running

    python main_fast.py [--sensitivity MULTIPLIER] [--debug]

- `--sensitivity MULTIPLIER` -- mouse-speed multiplier. Defaults to
  whatever's saved in settings (`1.0` the first time you run it). `1.5`
  moves the cursor faster, `0.5` slower. A multiplier on top of
  `constants.MOUSE_SPEED`. Passing it here overrides (and re-saves) the
  settings value; it's also changeable at runtime from the Settings window.
- `--debug` -- defaults to whatever's saved in settings (off the first
  time you run it). See "Debug mode" below. Also toggleable at runtime
  from the Settings window.

## The control bar

A small always-visible bar sits in the very bottom-right corner of the
screen, regardless of Mouse/Keyboard mode or debug state -- so there's
always a way to pause, get help, or quit without needing a free hand to
gesture with, or to already know a gesture at all:

- A status dot + label -- green **FingerWorks** when active, orange
  **Paused** when paused.
- A **Move hand closer** / **Move hand back** hint, shown only when your
  (right/mouse) hand is currently outside the distance-from-camera range
  the gesture cutoffs assume -- see "Hand-to-camera distance" below.
- **Pause / Resume** -- stops all hand tracking and gesture processing
  (the camera keeps running, just isn't acted on) until you resume. Useful
  for stepping away or using your physical mouse/keyboard for a bit
  without quitting the program outright.
- **Help** -- opens a quick gesture cheat sheet (see "Gestures" below).
- **Settings** -- opens the Settings window (see "Settings" below).
- **Quit** -- quits the program. Same effect as Escape. (The thumb+pinky
  gesture that used to quit now pauses instead -- see "Gestures" below --
  so quitting always needs a deliberate click/Escape, never an accidental
  gesture mid-use.)

## Settings

Click **Settings** in the control bar to open a small settings window:

- **Camera** -- a dropdown of detected cameras, plus **Auto
  (recommended)**, which is the default: it picks the first camera that
  opens, same as always. Pick a specific camera to pin it explicitly
  (e.g. if you have more than one webcam and auto-pick chooses the wrong
  one) -- it stays pinned across restarts until you set it back to Auto.
  Changing it applies immediately, no restart needed.
- **Mouse sensitivity** -- same multiplier as `--sensitivity`, as a
  slider.
- **Debug mode** -- same as `--debug`, as a checkbox; applies immediately.
- **Type into the keyboard's own area** -- off by default. Off, the
  on-screen keyboard types into whatever text box/app actually has OS
  focus, just like a physical keyboard. On, keys only build up the
  keyboard's own preview line instead (the original behavior), which you
  then move elsewhere yourself with the `Copy Typed`/`Cut Typed` keys.
  Applies immediately.

Hit **Apply** to save and apply, or **Cancel**/close the window to discard.
Settings are saved to `~/.finger_works_settings.json` and persist across
restarts; a `--sensitivity`/`--debug` command-line flag overrides the
saved value for that run (and re-saves it).

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
  `Keyboard`), the current mouse-sensitivity multiplier (`Sensitivity:
  1.0x`, from `--sensitivity`), and -- next to the action text -- which
  detected hand is doing what, e.g. `Mousing  [Right [Mouse]]`, or with a
  left hand also in frame, `Mousing  [Right [Mouse, scale=142], Left
  [Zoom: open, normal] [Paste: neither (none out)] [Scroll: neither (none
  out)]]`. The `scale=NNN` next to `Right [Mouse` is the live
  wrist-to-knuckle "hand scale" the distance hint is based on -- see
  "Hand-to-camera distance" below for calibrating `HAND_SCALE_REFERENCE`
  off this number.
- A second always-on-top window (top-left corner) shows the **live camera
  feed**, with each detected hand's skeleton traced over it in real time
  and its current gesture labeled right next to it (cyan for the right/
  mouse hand, magenta for the left/zoom-paste hand). This is purely
  cosmetic -- it doesn't change how any gesture is recognized or acted on
  -- but it's the fastest way to see at a glance exactly what the tracker
  sees and how it's reading your hand, live, rather than only reading the
  text description of it.
  - The `Right [...]` bracket shows which hand is driving the mouse/
    keyboard, or `Right [ignored]` if a second hand also read as "Right".
  - The `Left [Zoom: ...]` bracket shows the zoom gesture's live pose
    (`open`/`fist`/`neither (<fingers> out)`) and whether the screen is
    currently zoomed in (`zoomed`/`normal`); `-> sent zoom-in` / `-> sent
    zoom-out` is appended the instant a zoom action actually fires.
  - The `Left [Paste: ...]` bracket shows the paste gesture's live pose
    (`scissors`/`neither (<fingers> out)`); `-> sent paste` is appended the
    instant paste actually fires.
  - The `Left [Scroll: ...]` bracket shows the scroll gesture's live pose
    (`pointing (up)`/`pointing (down)`/`pointing (sideways)`/`neither
    (<fingers> out)`); `-> scrolling up`/`-> scrolling down` is appended
    while it's actively driving a scroll.
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
| Thumb + pinky extended, other three folded | Pause tracking (same as the control bar's Pause button). Resume from the control bar. |

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
| Index finger extended and aimed upward, others folded | Scroll up. Held continuously -- keeps scrolling for as long as the pose and direction are held, paced to a tick every `SCROLL_FRAME_INTERVAL` frames (not every frame) so it reads as a controlled scroll rather than a fast, disorientating flick. |
| Index finger extended and aimed downward, others folded | Scroll down (same pose, opposite direction). |

The scroll gesture's direction comes from the index finger's own angle
(fingertip relative to its base knuckle), not its position relative to the
wrist -- pointing mostly sideways does nothing rather than guessing a
direction.

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

## Hand-to-camera distance

Every gesture cutoff (`FINGER_OUT_CUTOFF`, `LEFT_CLICK_CUTOFF`,
`RIGHT_CLICK_CUTOFF`) is a raw camera-frame pixel distance, which
implicitly assumes your hand is roughly a certain size on screen -- i.e. a
certain distance from the camera. Too close and pinches can read as "not
quite together" even when your fingers are touching; too far and folded
fingers can still read as extended, or a pinch never quite registers as
closed. That's the "there's an optimal distance" effect.

The control bar shows **Move hand closer** / **Move hand back** next to
the status dot whenever your (right/mouse) hand drifts outside the
comfortable band around `HAND_SCALE_REFERENCE` in `constants.py`, so a
gesture not registering has an obvious first thing to check, rather than
looking like flaky tracking. It's based on your hand's live
wrist-to-middle-knuckle pixel distance (`mouse_control.hand_scale()`) --
stable across hand poses, unlike a fingertip-based measurement -- shown
live in `--debug` as `scale=NNN` next to `Right [Mouse`.

`HAND_SCALE_REFERENCE`'s shipped value is a rough placeholder, not
calibrated to any particular camera. To calibrate it for yours: run with
`--debug`, hold your hand where clicks and poses register reliably, note
the `scale=NNN` value, and set `HAND_SCALE_REFERENCE` to it.

This is a hint, not a fix -- the underlying cutoffs are still raw pixel
distances, so there's still a real sweet spot; the hint just tells you
when you've left it. Making the gesture cutoffs themselves
distance-independent (normalizing every pixel distance by hand scale
before comparing it to a cutoff, instead of comparing raw pixels) would
remove the sweet spot rather than just flagging when you're outside it --
a larger change than this hint, left for later since it touches every
tuned cutoff in `constants.py` at once.

### On-screen keyboard keys

Once the keyboard is toggled on (right-hand fist), it's laid out roughly
like a physical/phone keyboard: `Tab`, `Caps`, and one `Shift` down the
left side of the QWERTY block, `Enter` and the other `Shift` on the right,
a wide `Space` bar along the bottom. The remaining actions below have no
physical-keyboard spot of their own, so they get their own row underneath
`Space`.

| Key | Action |
|---|---|
| `Space` | Types a space. |
| `Enter` | Sends Enter/Return. |
| `Tab` | Sends Tab. |
| `⌫` | Backspace. (Deliberately not the literal character `<` -- the symbols page has an actual `<` key, and reusing it for backspace would make that key erase instead of typing a less-than sign.) |
| `Clear` | Clears this keyboard's own typed-text preview line only (not anything on your desktop). |
| `Copy` | Sends a real Ctrl+C -- copies whatever's currently selected elsewhere on your desktop. |
| `Cut` | Sends a real Ctrl+X. |
| `Copy Typed` | Copies this keyboard's own typed-text buffer (the preview line, not your desktop selection) to the OS clipboard. |
| `Cut Typed` | Same, then clears the preview line. Also reachable via the right-hand "scissors" gesture. |
| `Paste` | Reads the OS clipboard and types its contents as real keystrokes. Also reachable via the left-hand "scissors" gesture, without opening the keyboard. |
| `Shift` | Capitalizes the *next* letter only, then turns itself back off -- like a phone keyboard. Letter keys visibly flip to uppercase while it's active. |
| `Caps` | Toggles Caps Lock -- letters stay uppercase until you press it again. Independent of `Shift`. |
| `Undo` | Sends Ctrl+Z (Cmd+Z on macOS). |
| `Redo` | Sends Ctrl+Y (Cmd+Shift+Z on macOS). |
| `Select All` | Sends Ctrl+A (Cmd+A on macOS) -- selects everything in whatever's focused, same as `Copy`/`Cut`. |
| `123` / `ABC` | Switches the three letter rows to a symbols page (common punctuation and math symbols -- see below) and back, like a phone keyboard's mode key. The digit row on top stays put either way. |

The symbols page: `! @ # $ % ^ & * ( ) - _ = + [ ] { } | ~ ` : " ' < > ? ,`

Letters are typed lowercase by default and uppercase while `Shift`/`Caps`
is active, matching whatever's currently shown on the button -- via
`pyautogui.typewrite()` rather than `press()`, so shifted punctuation (on
the symbols page, or anywhere else) comes out correct without needing
special-casing for each character.

## Parameters (`constants.py`)

| Parameter | Meaning |
|---|---|
| `FINGER_OUT_CUTOFF` | Wrist-relative pixel distance above which a fingertip counts as "extended" rather than folded. Drives every pose gesture (fist, scissors, zoom's open-hand/fist). Raise if poses aren't registering as extended when they should; lower if folded fingers are misread as extended. |
| `LEFT_CLICK_CUTOFF` | Max thumb-to-index pixel distance that counts as a left-click pinch. Higher = a lighter tap triggers a click; too high risks false clicks from your hand's normal resting/aiming pose. |
| `RIGHT_CLICK_CUTOFF` | Same, for thumb-to-ring (right-click pinch). |
| `SCROLL_VEL_CUTOFF` | (Reserved; unused now that scrolling is pose-based -- see `INDEX_MCP_IDX`/`SCROLL_AMOUNT`/`SCROLL_FRAME_INTERVAL`.) |
| `INDEX_MCP_IDX` | Landmark index for the index finger's base knuckle -- used with `INDEX_IDX` to read the index finger's pointing direction for the scroll gesture. |
| `SCROLL_AMOUNT` | How far one scroll tick moves (in `pyautogui.scroll()` units) while the point-up/point-down gesture is held. |
| `SCROLL_FRAME_INTERVAL` | Send a scroll tick only every this-many-th held frame, instead of every camera frame -- paces continuous scrolling down to something controllable. Raise to slow scrolling down, lower (min 1) to speed it up. |
| `HAND_SCALE_REFERENCE` | Wrist-to-middle-knuckle pixel distance the gesture cutoffs assume ("how big your hand should look"). Drives the control bar's Move-closer/Move-back hint -- see "Hand-to-camera distance" above for how to calibrate it. |
| `HAND_SCALE_TOO_CLOSE_RATIO` / `HAND_SCALE_TOO_FAR_RATIO` | Live-scale-to-`HAND_SCALE_REFERENCE` ratio bounds outside which the Move-closer/Move-back hint fires. |
| `MOUSE_X_SENS` / `MOUSE_Y_SENS` | Per-axis scale applied when mapping the fingertip's position in the camera frame onto screen coordinates. |
| `MOUSE_SPEED` | Fraction of the remaining distance to the target the cursor closes each frame (exponential smoothing). Higher tracks the fingertip more tightly; lower is smoother but laggier. Also scaled by `--sensitivity` at runtime. |
| `ZOOMED_MOUSE_SPEED_FACTOR` | Multiplies `MOUSE_SPEED` while the zoom gesture has the screen zoomed in, since the same hand movement then covers much more of the visible area. |
| `MIN_DETECTION_CONFIDENCE` / `MIN_TRACKING_CONFIDENCE` | How confident MediaPipe's hand-landmark model must be before it reports/keeps tracking a hand. Lower (e.g. 0.5/0.4) if tracking drops out with gloves on; trades some false-positive/jitter risk for better detection. See "Using this with gloves on" in `README.md`. |
| `SWAP_LABELED_HANDS` | Flips MediaPipe's Left/Right hand label for every detected hand, every frame. Set if mouse/keyboard control and zoom/paste ever come out swapped for your camera setup (e.g. your right hand ends up zooming instead of mousing). |
