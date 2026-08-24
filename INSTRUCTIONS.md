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
- Its own border flashes on every left/right click -- green for left,
  yellow for right -- for about 150ms, regardless of the Click sounds
  setting. See `overlay.flash_click_feedback()`; this exists as click
  confirmation that doesn't depend on your OS/audio setup working, unlike
  the (optional) click sound.
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
  slider. Governs how fast the cursor closes the gap to wherever it's
  currently aiming (`constants.MOUSE_SPEED`).
- **Cursor snappiness** -- a slider from 0.0 (max smoothing -- steadiest,
  but small precise movements can feel like the cursor is "sliding"/
  lagging behind your fingertip) to 1.0 (max snappiness -- tracks small
  movements almost immediately, at the cost of more visible raw hand-
  tracking jitter). A separate knob from Mouse sensitivity above: that one
  governs how fast the cursor closes in on an already-computed target
  position; this one governs how readily small fingertip movements even
  *move* that target in the first place, which is what mainly reads as
  "sliding" when it's too heavily smoothed. See
  `constants.JITTER_ALPHA_MIN`/`JITTER_ALPHA_MAX`.
- **Scroll speed** -- multiplies `constants.SCROLL_AMOUNT` for the
  left-hand scroll gesture (see "Left hand -- zoom, paste & scroll"
  below).
- **Keyboard size** -- scales the overlay panel (and so the on-screen
  keyboard drawn on it) up or down. The panel repositions itself to stay
  clear of the control bar at any size.
- **Click sounds** / **Keyboard sounds** -- both off by default. A short,
  quiet tone on every left/right-click, or every on-screen keyboard key
  press, respectively -- see `sounds.py`. Deliberately light rather than
  an obvious "beep"; if you want them louder/different, `generate_sounds.py`
  regenerates `sounds/click.wav`/`sounds/key.wav` from adjustable
  parameters. Playback needs no extra dependency: a background thread
  plays sounds one at a time via a per-platform system player
  (`winsound`/`afplay`/`aplay`), which is what keeps fast repeated
  triggers (e.g. quickly switching keys) from ever racing each other and
  dropping a sound.
- **Debug mode** -- same as `--debug`, as a checkbox. Session-only,
  unlike every other setting here: it's never saved to
  `~/.finger_works_settings.json`, so it's always back off the next time
  you start the program even if you leave it checked now.

**Reset to Defaults** resets every field in this window back to its
default value (without applying or saving anything by itself -- hit
**Apply** afterward to actually use them, or **Cancel** to back out of
the reset too). Hit **Apply** to save and apply everything else, or
**Cancel**/close the window to discard. Settings (other than Debug mode)
are saved to `~/.finger_works_settings.json` and persist across restarts;
a `--sensitivity`/`--debug` command-line flag overrides the in-memory
value for that run (`--sensitivity` is then also re-saved; `--debug`
never persists either way).

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
  detected hand is doing what, e.g. `Mousing  [Right [Mouse, scale=228]]`,
  or with a left hand also in frame, `Mousing  [Right [Mouse, scale=228],
  Left [Zoom: open, normal] [Paste: neither (none out)] [Scroll: neither
  (none out)]]`. The `scale=NNN` next to `Right [Mouse` is the live
  wrist-to-knuckle pixel size gesture cutoffs are normalized against this
  frame -- see "Hand-to-camera distance" below for calibrating
  `HAND_SCALE_TUNING_REFERENCE` off it.
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
    -- `pointing (up)`/`pointing (sideways)` for the index-up pose,
    `thumb (down)`/`thumb (sideways)`/`thumb (up)` for the thumb-down
    pose, or `neither (<fingers> out)` if neither pose is held; `->
    scrolling up`/`-> scrolling down` is appended while it's actively
    driving a scroll.
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

### Left hand -- zoom, paste & scroll

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
| Index finger extended and aimed upward, others folded | Scroll up. Held continuously -- keeps scrolling for as long as the pose and direction are held, sent in small ticks every `SCROLL_FRAME_INTERVAL` frame(s) rather than infrequent big jumps, so it reads as a smooth, controlled scroll rather than a choppy or disorientating one. |
| Thumb extended and aimed downward, others folded ("thumbs down") | Scroll down. Deliberately a different finger from scroll-up, not the same pose pointed the other way -- see below. |

Each scroll direction's finger has its own angle read separately: index's
fingertip relative to its own base knuckle for scroll-up, thumb's fingertip
relative to its own base knuckle for scroll-down. Pointing mostly sideways
does nothing rather than guessing a direction, for either one.

Scroll-down used to be the same pose as scroll-up (index only, pointed
down instead of up), but that turned out to misfire as zoom's open-hand
gesture in practice: aiming the index finger downward is a less natural
hand angle than aiming it up, and the slight extra curl that takes was
enough to also read the other fingers as "extended" right at
`FINGER_OUT_CUTOFF`'s edge -- which is exactly zoom's pose. Using the
thumb instead (a different finger, with a different resting curl) avoids
scroll-down being only a directional flip of a gesture that's prone to
that particular confusion.

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

Gesture cutoffs (`FINGER_OUT_CUTOFF`, `LEFT_CLICK_CUTOFF`,
`RIGHT_CLICK_CUTOFF`) are compared against every landmark position only
*after* it's been divided by the hand's own live wrist-to-middle-knuckle
pixel distance (`mouse_control.hand_scale()` /
`mouse_control.normalize_landmarks()`, applied once per hand per frame in
`main_fast.py`) -- so they're unitless ratios of the hand's own size, not
raw pixel counts. A hand that's closer to the camera has both a bigger raw
fingertip distance *and* a bigger reference size, so the ratio stays the
same either way. In short: there's no "optimal distance" to find -- move
closer or farther and gestures should keep registering the same way.

Each cutoff's value in `constants.py` is still derived from (divided by
150 against) the old pixel-tuned numbers, so the *feel* at a typical
webcam distance is unchanged from before this normalization existed --
only the requirement to stay at roughly that one distance is gone. If
gestures still feel off for your hand/camera/lighting, retune the ratios
directly the same way the old pixel values were documented as needing
retuning -- see each constant's comment.

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
| `FINGER_OUT_CUTOFF` | Wrist-relative distance, as a ratio of the hand's own live size (see "Hand-to-camera distance" above), above which a fingertip counts as "extended" rather than folded. Drives every pose gesture (fist, scissors, zoom's open-hand/fist, scroll's point-up/down). Raise if poses aren't registering as extended when they should; lower if folded fingers are misread as extended. |
| `LEFT_CLICK_CUTOFF` | Max thumb-to-index distance (same hand-scale-relative ratio) that counts as a left-click pinch. Higher = a lighter tap triggers a click; too high risks false clicks from your hand's normal resting/aiming pose. |
| `RIGHT_CLICK_CUTOFF` | Same, for thumb-to-ring (right-click pinch). |
| `SCROLL_VEL_CUTOFF` | (Reserved; unused now that scrolling is pose-based -- see `INDEX_MCP_IDX`/`THUMB_MCP_IDX`/`SCROLL_AMOUNT`/`SCROLL_FRAME_INTERVAL`.) |
| `INDEX_MCP_IDX` | Landmark index for the index finger's base knuckle -- used with `INDEX_IDX` to read the index finger's pointing direction for scroll-up. |
| `THUMB_MCP_IDX` | Same idea, for the thumb's base knuckle -- used with `THUMB_IDX` to read the thumb's pointing direction for scroll-down. |
| `SCROLL_AMOUNT` | How far one scroll tick moves (in `pyautogui.scroll()` units) while a scroll gesture is held, sent every `SCROLL_FRAME_INTERVAL` frame(s). Tuned together with `SCROLL_FRAME_INTERVAL` (a smaller amount sent more often at the same overall amount/interval ratio scrolls just as fast but smoother; the same total delivered in fewer, bigger ticks reads as choppy) -- retune both together, or leave this alone and use the Settings "Scroll speed" slider instead. |
| `SCROLL_FRAME_INTERVAL` | Send a scroll tick only every this-many-th held frame, instead of every camera frame. See `SCROLL_AMOUNT` above -- these two are a pair. |
| `MOUSE_X_SENS` / `MOUSE_Y_SENS` | Per-axis scale applied when mapping the fingertip's position in the camera frame onto screen coordinates. |
| `MOUSE_SPEED` | Fraction of the remaining distance to the target the cursor closes each frame (exponential smoothing). Higher tracks the fingertip more tightly; lower is smoother but laggier. Also scaled by `--sensitivity` at runtime. |
| `ZOOMED_MOUSE_SPEED_FACTOR` | Multiplies `MOUSE_SPEED` while the zoom gesture has the screen zoomed in, since the same hand movement then covers much more of the visible area. |
| `MIN_DETECTION_CONFIDENCE` / `MIN_TRACKING_CONFIDENCE` | How confident MediaPipe's hand-landmark model must be before it reports/keeps tracking a hand. Lower (e.g. 0.5/0.4) if tracking drops out with gloves on; trades some false-positive/jitter risk for better detection. See "Using this with gloves on" in `README.md`. |
| `SWAP_LABELED_HANDS` | Flips MediaPipe's Left/Right hand label for every detected hand, every frame. Set if mouse/keyboard control and zoom/paste ever come out swapped for your camera setup (e.g. your right hand ends up zooming instead of mousing). |
