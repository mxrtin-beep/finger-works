
import sys
import tkinter as tk

import settings as fw_settings


# Maps a button's logical state (set by keyboard.execute_event_keyboard) to
# a fill color for drawing. Kept as plain state names rather than raw color
# tuples so keyboard.py doesn't need to know anything about how it's drawn.
_STATE_COLORS = {
	'idle': '#3a3a3a',
	'hover': '#2ecc71',
	'active': '#e74c3c',
}

# These keyboard labels get a somewhat larger font than other
# multi-character labels (see draw()) -- they're the widest/most
# prominent keys (the physical-keyboard-style structural keys, Space, and
# the other keys called out as wanting more visual weight), so they can
# afford to stand out a bit more than a plain utility label like 'Clear'
# or 'Paste'.
_EMPHASIZED_LABELS = {
	'Tab', 'Caps', 'Shift', 'Enter', 'Undo', 'Redo', 'Space', 'Select All', '123', 'ABC',
}

# Two-word labels narrow enough relative to their text that splitting them
# onto two lines is what makes them fit their button (see draw()) --
# 'Select All' isn't: its button is wide enough for the whole label on one
# line, so splitting it just made the two lines overlap instead of helping.
_TWO_LINE_LABELS = {'Copy Typed', 'Cut Typed'}

# Simple text-and-emoji cheat sheet shown in the Help window -- a quick
# visual reminder of the gestures, not a replacement for the full reference
# in INSTRUCTIONS.md (which also covers every tunable parameter).
_INSTRUCTIONS_TEXT = """RIGHT HAND -- mouse & keyboard

 ✋  Move your hand -- moves the cursor
 \U0001F90F  Pinch thumb + index -- left click
 \U0001F90F  Pinch thumb + ring -- right click
 ✊  Closed fist -- toggle on-screen keyboard
 ✌  Index + middle out ("scissors") -- cut typed text
 \U0001F919  Thumb + pinky out, others folded -- pause


LEFT HAND -- zoom & paste

 ✋  Open hand, all 5 fingers out -- zoom in
 ✊  Closed fist -- zoom out
 ✌  Index + middle out ("scissors") -- paste
 \U0001F446  Point up (index only, aimed up) -- scroll up
 \U0001F44E  Thumb down (thumb only, aimed down) -- scroll down


See INSTRUCTIONS.md in the project folder for the full
gesture and parameter reference.
"""


def _rgb_to_hex(rgb):
	r, g, b = rgb
	return f'#{r:02x}{g:02x}{b:02x}'


def _make_window_noactivate(hwnd):
	"""Best-effort, Windows only: mark this window as one that never
	receives keyboard focus.

	Without this, there's no guarantee our own overlay window can't end up
	with keyboard focus at some point (e.g. window-manager quirks around
	topmost/override-redirect windows). If that happened while typing,
	real keystrokes -- including the Cut/Copy/Paste hotkeys -- would go to
	this invisible panel instead of whatever app the user is actually
	using. Setting WS_EX_NOACTIVATE at the OS level rules that out
	entirely, rather than hoping it never happens.
	"""
	if sys.platform != 'win32':
		return
	try:
		import ctypes
		GWL_EXSTYLE = -20
		WS_EX_NOACTIVATE = 0x08000000
		WS_EX_TOOLWINDOW = 0x00000080
		user32 = ctypes.windll.user32
		style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
		user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
	except Exception as exc:
		print(f'[WARN] Could not set no-activate window style: {exc}')


def _make_flat_button(parent, text, command, bg='#3a3a3a'):
	return tk.Button(
		parent, text=text, command=command, bg=bg, fg='white',
		activebackground='#555555', activeforeground='white',
		relief='flat', font=('Segoe UI', 9), padx=8, pady=3,
		highlightthickness=0, bd=0,
	)


class Overlay:
	"""A fixed, always-on-top panel docked in the corner of the screen.

	Shows the current action/mode as text, and (in Keyboard mode) the
	on-screen keyboard -- all in real screen coordinates, the same space
	the OS mouse cursor lives in, so hit-testing a key against the real
	cursor position is a plain coordinate comparison, not a translation
	between two different coordinate spaces.

	Also owns a small always-visible control bar (status indicator,
	Pause/Resume, Help, Settings, Quit) docked in the very corner of the
	screen, independent of Mouse/Keyboard/debug state -- so there's always
	a way to pause, get help, or quit without needing to already know a
	gesture for it.
	"""

	def __init__(self, screen_width, screen_height, panel_width=None, panel_height=None, margin=None,
				debug=False, mouse_sensitivity=1.0, keyboard_scale=1.0,
				on_settings_changed=None, get_settings=None, get_available_cameras=None):
		self.screen_width = screen_width
		self.screen_height = screen_height

		# Everything below is sized as a fraction of *this* screen
		# (clamped to a sane min/max) rather than a fixed pixel count, so
		# the control bar, panel margins, and debug video window look like
		# the same proportion of the screen on a small laptop panel and a
		# large 4K monitor alike, instead of a fixed-pixel size that would
		# look tiny on one and oversized on the other. `margin`/
		# `panel_width`/`panel_height` can still be passed explicitly
		# (e.g. by a test) to override any of this.
		def scaled(fraction_of, frac, lo, hi):
			return max(lo, min(hi, round(fraction_of * frac)))

		self._margin = margin if margin is not None else scaled(screen_width, 0.014, 14, 30)

		# Off by default: the panel then only appears while the on-screen
		# keyboard is toggled on (it needs to be visible to aim clicks at
		# its keys), and no debug text is drawn even then. With debug on,
		# the panel is up at all times -- including in Mouse mode -- and
		# shows the debug text (current event, hand routing, zoom/paste
		# gesture state), same as before this flag existed.
		self.debug = debug

		# Echoed on the debug panel and prefilled into the Settings window;
		# kept in sync with the real value (mouse_control's own sensitivity
		# multiplier) by whoever calls set_sensitivity() after a settings
		# change, rather than this class owning that value itself.
		self.mouse_sensitivity = mouse_sensitivity

		# Callbacks into main_fast.py, since this class shouldn't need to
		# know how to reopen a camera or write settings.json itself:
		# - on_settings_changed(new_settings_dict): called when the user
		#   hits Apply in the Settings window.
		# - get_settings() -> dict: current effective settings, used to
		#   prefill the Settings window each time it's opened.
		# - get_available_cameras() -> list[int]: probed lazily, only when
		#   the Settings window is opened (probing is a bit slow).
		self.on_settings_changed = on_settings_changed
		self.get_settings = get_settings
		self.get_available_cameras = get_available_cameras

		self.paused = False

		# Base (keyboard_scale == 1.0) panel fractions, kept around so
		# set_keyboard_scale() can recompute panel_width/height from scratch
		# rather than compounding scale factors onto an already-scaled size.
		self._base_panel_width = int(screen_width * 0.42)
		self._base_panel_height = int(screen_height * 0.34)

		self.keyboard_scale = keyboard_scale
		self.panel_width = panel_width or round(self._base_panel_width * keyboard_scale)
		self.panel_height = panel_height or round(self._base_panel_height * keyboard_scale)

		# The control bar sits in the actual bottom-right corner; the main
		# panel (keyboard/debug text) sits directly above it, so the two
		# never overlap regardless of which is currently visible.
		#
		# control_width itself is set later, in _build_control_bar(), sized
		# to fit its actual buttons/labels rather than guessed as a screen
		# fraction here -- a fixed fraction wide enough for the longest
		# label ('Settings') left visible empty space to the right of Quit
		# on most screens. origin_y below only depends on control_height,
		# which is still a screen fraction (nothing to fit it to), so
		# nothing here needs control_width's later, more-accurate value.
		self.control_height = scaled(screen_height, 0.032, 36, 56)

		# pyautogui.size() (screen_width/height here) reports the full
		# display resolution, not the desktop work area -- it doesn't know
		# about the taskbar at all. A plain `margin` from the true bottom
		# edge lands partly underneath a normal-height Windows/macOS/Linux
		# taskbar or dock, which is what clipped the control bar. This
		# floors the bottom clearance well above any of those (taskbars
		# commonly run 40-56px, a bit more on a high-DPI/large monitor) so
		# the bar clears it and hovers just above, while `margin` still
		# governs the right-edge gap as before.
		self._bottom_clearance = scaled(screen_height, 0.06, 64, 110)

		self.origin_x = screen_width - self.panel_width - self._margin
		self.origin_y = (
			screen_height - self.panel_height - self.control_height
			- self._margin - self._bottom_clearance
		)

		self.root = tk.Tk()
		self.root.title('finger-works')
		self.root.overrideredirect(True)        # no title bar/border
		self.root.attributes('-topmost', True)  # always on top of other windows
		self.root.geometry(
			f'{self.panel_width}x{self.panel_height}+{self.origin_x}+{self.origin_y}'
		)

		self.should_quit = False
		self.root.bind('<Escape>', lambda _event: self._quit())
		self.root.protocol('WM_DELETE_WINDOW', self._quit)

		self.root.update_idletasks()  # make sure the real window/HWND exists
		_make_window_noactivate(self.root.winfo_id())

		self.canvas = tk.Canvas(
			self.root,
			width=self.panel_width,
			height=self.panel_height,
			bg='#1e1e1e',
			highlightthickness=2,
			highlightbackground='#4a4a4a',
			highlightcolor='#4a4a4a',
		)
		self.canvas.pack(fill='both', expand=True)

		# Tracks whether the main panel is currently mapped, so draw() only
		# calls withdraw()/deiconify() on an actual change instead of every
		# frame (redundant, but also deiconify() steals focus back on some
		# window managers if called needlessly).
		self._visible = True
		if not self.debug:
			self.root.withdraw()
			self._visible = False

		# The live camera feed (hand skeleton traced over the raw video,
		# gestures labeled as they happen) is purely a "look impressive"
		# debug aid -- it doesn't affect how the mouse/keyboard is driven
		# at all -- so it only exists when debug is on, as a separate
		# always-on-top window rather than fighting the main panel's fixed
		# layout for space. set_debug() can create/destroy it later too, so
		# toggling debug in the Settings window takes effect immediately.
		self.video_canvas = None
		self.video_width = None
		self.video_height = None
		self._video_photo = None  # keep a reference so Tk doesn't GC the image
		if self.debug:
			self._create_video_window()

		self._settings_win = None
		self._instructions_win = None
		self._build_control_bar()

	# --- Control bar --------------------------------------------------

	def _build_control_bar(self):
		self.control_window = tk.Toplevel(self.root)
		self.control_window.title('finger-works -- controls')
		self.control_window.overrideredirect(True)
		self.control_window.attributes('-topmost', True)
		# No explicit size yet -- set below, after the buttons are packed,
		# to whatever width they actually need (see the update_idletasks()
		# call at the end of this method).
		self.control_window.configure(bg='#1e1e1e')
		self.control_window.bind('<Escape>', lambda _event: self._quit())
		self.control_window.protocol('WM_DELETE_WINDOW', self._quit)

		frame = tk.Frame(
			self.control_window, bg='#1e1e1e',
			highlightthickness=2, highlightbackground='#4a4a4a', highlightcolor='#4a4a4a',
		)
		frame.pack(fill='both', expand=True)

		inner = tk.Frame(frame, bg='#1e1e1e')
		inner.pack(fill='both', expand=True, padx=6, pady=4)
		frame = inner

		self.status_canvas = tk.Canvas(
			frame, width=14, height=14, bg='#1e1e1e', highlightthickness=0,
		)
		self.status_dot = self.status_canvas.create_oval(2, 2, 12, 12, fill='#2ecc71', outline='')
		self.status_canvas.pack(side='left', padx=(4, 6))

		self.status_label = tk.Label(
			frame, text='FingerWorks', fg='#dddddd', bg='#1e1e1e',
			font=('Segoe UI', 9, 'bold'),
		)
		self.status_label.pack(side='left', padx=(0, 6))

		self.pause_button = _make_flat_button(frame, 'Pause', self._toggle_pause)
		self.pause_button.pack(side='left', padx=2)
		_make_flat_button(frame, 'Help', self._open_instructions).pack(side='left', padx=2)
		_make_flat_button(frame, 'Settings', self._open_settings).pack(side='left', padx=2)
		_make_flat_button(frame, 'Quit', self._quit, bg='#7a2e2e').pack(side='left', padx=2)

		# Now that every button/label is packed, size the window to what
		# it actually needs -- a floor still applies so it can't shrink to
		# something absurd if the content here ever changes drastically,
		# but there's no longer a fixed-fraction ceiling leaving empty
		# space past the last button.
		self.control_window.update_idletasks()
		self.control_width = max(200, self.control_window.winfo_reqwidth())
		cx = self.screen_width - self.control_width - self._margin
		cy = self.screen_height - self.control_height - self._bottom_clearance
		self.control_window.geometry(
			f'{self.control_width}x{self.control_height}+{cx}+{cy}'
		)

		_make_window_noactivate(self.control_window.winfo_id())

		self._refresh_pause_ui()

	def _toggle_pause(self):
		self.set_paused(not self.paused)

	def set_paused(self, paused):
		"""Pause/resume hand tracking. Public so main_fast.py can call it
		too -- the thumb+pinky gesture pauses the program (rather than
		quitting it, as it originally did), same as clicking Pause/Resume
		here."""
		self.paused = paused
		self._refresh_pause_ui()

	def _refresh_pause_ui(self):
		if self.paused:
			self.status_canvas.itemconfig(self.status_dot, fill='#e67e22')
			self.status_label.config(text='Paused')
			self.pause_button.config(text='Resume')
		else:
			self.status_canvas.itemconfig(self.status_dot, fill='#2ecc71')
			self.status_label.config(text='FingerWorks')
			self.pause_button.config(text='Pause')

	# --- Settings window ------------------------------------------------

	def _open_settings(self):
		if self._settings_win is not None and self._settings_win.winfo_exists():
			self._settings_win.lift()
			return

		current = self.get_settings() if self.get_settings else {}
		cameras = self.get_available_cameras() if self.get_available_cameras else []

		win = tk.Toplevel(self.root)
		self._settings_win = win
		win.title('FingerWorks Settings')
		win.attributes('-topmost', True)
		win.configure(bg='#1e1e1e')
		win.resizable(False, False)

		def close():
			win.destroy()
			self._settings_win = None

		win.protocol('WM_DELETE_WINDOW', close)
		win.bind('<Escape>', lambda _event: close())

		label_opts = dict(fg='#dddddd', bg='#1e1e1e', font=('Segoe UI', 10))

		tk.Label(win, text='Camera', **label_opts).grid(
			row=0, column=0, sticky='w', padx=10, pady=(12, 4))

		camera_labels = ['Auto (recommended)'] + [f'Camera {i}' for i in cameras]
		current_device = current.get('camera_device')
		current_label = 'Auto (recommended)' if current_device is None else f'Camera {current_device}'
		if current_label not in camera_labels:
			# The previously-chosen camera isn't detected right now (e.g.
			# unplugged) -- still offer it so Apply doesn't silently
			# discard the user's choice, but it'll fail over to auto-pick
			# at runtime if it really isn't there (see main_fast.py).
			camera_labels.append(current_label)
		camera_var = tk.StringVar(value=current_label)
		tk.OptionMenu(win, camera_var, *camera_labels).grid(
			row=0, column=1, sticky='ew', padx=10, pady=(12, 4))

		tk.Label(win, text='Mouse sensitivity', **label_opts).grid(
			row=1, column=0, sticky='w', padx=10, pady=4)
		sens_var = tk.DoubleVar(value=current.get('sensitivity', 1.0))
		tk.Scale(
			win, from_=0.25, to=3.0, resolution=0.05, orient='horizontal',
			variable=sens_var, bg='#1e1e1e', fg='#dddddd', troughcolor='#3a3a3a',
			highlightthickness=0, length=180, showvalue=True,
		).grid(row=1, column=1, sticky='ew', padx=10, pady=4)

		# How readily the cursor responds to small fingertip movements --
		# low = steadier but can feel like it's "sliding"/lagging behind
		# small precise movements; high = tracks almost immediately but
		# shows more raw hand-tracking jitter. See constants.JITTER_ALPHA_MIN/
		# MAX and mouse_control.set_cursor_snappiness().
		tk.Label(win, text='Cursor snappiness', **label_opts).grid(
			row=2, column=0, sticky='w', padx=10, pady=4)
		snappiness_var = tk.DoubleVar(value=current.get('cursor_snappiness', 0.65))
		tk.Scale(
			win, from_=0.0, to=1.0, resolution=0.05, orient='horizontal',
			variable=snappiness_var, bg='#1e1e1e', fg='#dddddd', troughcolor='#3a3a3a',
			highlightthickness=0, length=180, showvalue=True,
		).grid(row=2, column=1, sticky='ew', padx=10, pady=4)

		tk.Label(win, text='Scroll speed', **label_opts).grid(
			row=3, column=0, sticky='w', padx=10, pady=4)
		scroll_speed_var = tk.DoubleVar(value=current.get('scroll_speed', 2.3))
		tk.Scale(
			win, from_=0.25, to=3.0, resolution=0.05, orient='horizontal',
			variable=scroll_speed_var, bg='#1e1e1e', fg='#dddddd', troughcolor='#3a3a3a',
			highlightthickness=0, length=180, showvalue=True,
		).grid(row=3, column=1, sticky='ew', padx=10, pady=4)

		tk.Label(win, text='Keyboard size', **label_opts).grid(
			row=4, column=0, sticky='w', padx=10, pady=4)
		keyboard_scale_var = tk.DoubleVar(value=current.get('keyboard_scale', 1.0))
		tk.Scale(
			win, from_=0.7, to=1.5, resolution=0.05, orient='horizontal',
			variable=keyboard_scale_var, bg='#1e1e1e', fg='#dddddd', troughcolor='#3a3a3a',
			highlightthickness=0, length=180, showvalue=True,
		).grid(row=4, column=1, sticky='ew', padx=10, pady=4)

		# Both off by default -- a short, quiet tone (see sounds.py), not
		# meant to be intrusive/annoying, so they're opt-in rather than
		# something everyone hears the first time they click or type.
		click_sounds_var = tk.BooleanVar(value=current.get('click_sounds', False))
		tk.Checkbutton(
			win, text='Click sounds', variable=click_sounds_var,
			fg='#dddddd', bg='#1e1e1e', selectcolor='#3a3a3a',
			activebackground='#1e1e1e', activeforeground='#dddddd',
		).grid(row=5, column=0, columnspan=2, sticky='w', padx=10, pady=4)

		keyboard_sounds_var = tk.BooleanVar(value=current.get('keyboard_sounds', False))
		tk.Checkbutton(
			win, text='Keyboard sounds', variable=keyboard_sounds_var,
			fg='#dddddd', bg='#1e1e1e', selectcolor='#3a3a3a',
			activebackground='#1e1e1e', activeforeground='#dddddd',
		).grid(row=6, column=0, columnspan=2, sticky='w', padx=10, pady=4)

		# Debug mode is deliberately excluded from "remembered for next
		# time" (see settings.py's _PERSISTED_KEYS) -- it only ever applies
		# to the run you turn it on for.
		debug_var = tk.BooleanVar(value=current.get('debug', False))
		tk.Checkbutton(
			win, text='Debug mode (event text + live camera view)', variable=debug_var,
			fg='#dddddd', bg='#1e1e1e', selectcolor='#3a3a3a',
			activebackground='#1e1e1e', activeforeground='#dddddd',
		).grid(row=7, column=0, columnspan=2, sticky='w', padx=10, pady=(4, 10))

		def apply_and_close():
			chosen = camera_var.get()
			camera_device = None if chosen.startswith('Auto') else int(chosen.split(' ')[1])
			new_settings = {
				'camera_device': camera_device,
				'sensitivity': round(sens_var.get(), 2),
				'debug': debug_var.get(),
				'cursor_snappiness': round(snappiness_var.get(), 2),
				'scroll_speed': round(scroll_speed_var.get(), 2),
				'keyboard_scale': round(keyboard_scale_var.get(), 2),
				'click_sounds': click_sounds_var.get(),
				'keyboard_sounds': keyboard_sounds_var.get(),
			}
			if self.on_settings_changed:
				self.on_settings_changed(new_settings)
			close()

		def reset_to_defaults():
			# Only resets what's shown in this window -- doesn't apply or
			# save anything by itself, so Cancel still discards a reset you
			# didn't mean to make, same as any other change here.
			d = fw_settings.DEFAULTS
			camera_var.set('Auto (recommended)')
			sens_var.set(d['sensitivity'])
			snappiness_var.set(d['cursor_snappiness'])
			scroll_speed_var.set(d['scroll_speed'])
			keyboard_scale_var.set(d['keyboard_scale'])
			click_sounds_var.set(d['click_sounds'])
			keyboard_sounds_var.set(d['keyboard_sounds'])
			debug_var.set(d['debug'])

		btn_frame = tk.Frame(win, bg='#1e1e1e')
		btn_frame.grid(row=8, column=0, columnspan=2, pady=(0, 10))
		_make_flat_button(btn_frame, 'Apply', apply_and_close, bg='#2ecc71').pack(side='left', padx=4)
		_make_flat_button(btn_frame, 'Cancel', close).pack(side='left', padx=4)
		_make_flat_button(btn_frame, 'Reset to Defaults', reset_to_defaults).pack(side='left', padx=4)

		win.update_idletasks()
		_make_window_noactivate(win.winfo_id())

	# --- Instructions/help window ---------------------------------------

	def _open_instructions(self):
		if self._instructions_win is not None and self._instructions_win.winfo_exists():
			self._instructions_win.lift()
			return

		win = tk.Toplevel(self.root)
		self._instructions_win = win
		win.title('FingerWorks -- Gestures')
		win.attributes('-topmost', True)
		win.configure(bg='#1e1e1e')

		def close():
			win.destroy()
			self._instructions_win = None

		win.protocol('WM_DELETE_WINDOW', close)
		win.bind('<Escape>', lambda _event: close())

		text = tk.Text(
			win, width=44, height=22, bg='#1e1e1e', fg='#eeeeee', relief='flat',
			font=('Segoe UI', 11), wrap='word', padx=14, pady=12,
			highlightthickness=0, bd=0,
		)
		text.insert('1.0', _INSTRUCTIONS_TEXT)
		text.config(state='disabled')
		text.pack(fill='both', expand=True)

		_make_flat_button(win, 'Close', close).pack(pady=(0, 10))

		win.update_idletasks()
		_make_window_noactivate(win.winfo_id())

	# --- Debug video window ----------------------------------------------

	def _create_video_window(self):
		# Scaled off screen width (clamped) rather than a fixed 480x360,
		# same reasoning as the control bar/margins above; kept at a 4:3
		# aspect ratio regardless of screen size.
		self.video_width = max(360, min(640, round(self.screen_width * 0.28)))
		self.video_height = round(self.video_width * 0.75)

		self.video_window = tk.Toplevel(self.root)
		self.video_window.title('finger-works -- camera')
		self.video_window.overrideredirect(True)
		self.video_window.attributes('-topmost', True)
		self.video_window.geometry(
			f'{self.video_width}x{self.video_height}+{self._margin}+{self._margin}'
		)
		self.video_window.bind('<Escape>', lambda _event: self._quit())
		self.video_window.protocol('WM_DELETE_WINDOW', self._quit)

		self.video_window.update_idletasks()
		_make_window_noactivate(self.video_window.winfo_id())

		self.video_canvas = tk.Canvas(
			self.video_window,
			width=self.video_width,
			height=self.video_height,
			bg='#000000',
			highlightthickness=2,
			highlightbackground='#4a4a4a',
			highlightcolor='#4a4a4a',
		)
		self.video_canvas.pack(fill='both', expand=True)

	def _destroy_video_window(self):
		self.video_window.destroy()
		self.video_canvas = None
		self.video_width = None
		self.video_height = None
		self._video_photo = None

	def set_debug(self, debug):
		"""Turn the debug text + live camera window on/off at runtime (e.g.
		from the Settings window), without needing to restart the
		program."""
		if debug == self.debug:
			return
		self.debug = debug
		if debug:
			self._create_video_window()
		else:
			self._destroy_video_window()

	def set_sensitivity(self, sensitivity):
		"""Update the sensitivity value shown on the debug panel. Doesn't
		itself change cursor speed -- that's mouse_control's own
		multiplier, set separately by whoever calls this (main_fast.py)."""
		self.mouse_sensitivity = sensitivity

	def set_keyboard_scale(self, scale):
		"""Resize the overlay panel (and so the on-screen keyboard drawn on
		it) to `scale` times its base size, at runtime -- e.g. from the
		Settings window's "Keyboard size" slider. No-op if unchanged.

		Only resizes/repositions the panel window and canvas here; the
		keyboard's actual button layout is a separate, static computation
		(keyboard.get_button_list) that main_fast.py must rebuild against
		the new self.panel_width/self.panel_height after calling this --
		this method doesn't do that itself since it has no reference to the
		current button list or keyboard page."""
		if scale == self.keyboard_scale:
			return
		self.keyboard_scale = scale
		self.panel_width = round(self._base_panel_width * scale)
		self.panel_height = round(self._base_panel_height * scale)

		# The panel sits directly above the control bar (see __init__), so
		# a taller panel needs to shift up to stay clear of it -- only
		# origin_y depends on panel_height; the control bar's own position
		# is independent of panel size and doesn't need to move.
		self.origin_x = self.screen_width - self.panel_width - self._margin
		self.origin_y = (
			self.screen_height - self.panel_height - self.control_height
			- self._margin - self._bottom_clearance
		)
		self.root.geometry(
			f'{self.panel_width}x{self.panel_height}+{self.origin_x}+{self.origin_y}'
		)
		self.canvas.config(width=self.panel_width, height=self.panel_height)

	def draw_video(self, frame_rgb):
		"""Show one camera frame (an RGB numpy array, already annotated with
		hand skeleton/gesture labels by the caller) in the debug video
		window. No-op when debug is off."""
		if self.video_canvas is None:
			return

		# Imported lazily so Pillow is only required when debug is
		# actually used, not for normal (non-debug) runs.
		from PIL import Image, ImageTk

		image = Image.fromarray(frame_rgb).resize((self.video_width, self.video_height))
		self._video_photo = ImageTk.PhotoImage(image)
		self.video_canvas.delete('all')
		self.video_canvas.create_image(0, 0, anchor='nw', image=self._video_photo)

	def _quit(self):
		self.should_quit = True

	def origin(self):
		"""(x, y) of this panel's top-left corner, in real screen coordinates.

		Used to convert the OS mouse cursor's screen position into this
		panel's local coordinate space for keyboard hit-testing.
		"""
		return self.origin_x, self.origin_y

	def pump(self):
		"""Process pending Tk events for one iteration of the main loop."""
		self.root.update_idletasks()
		self.root.update()

	def close(self):
		self.root.destroy()

	def draw(self, event_text, control_state, typed_preview, button_list, shift_active=False):
		# The panel itself is only up while there's something on it you
		# actually need (the on-screen keyboard, to aim clicks at its
		# keys) -- unless debug is on, in which case it's up all the time
		# so the debug text below is always visible, as it always used to
		# be before this flag existed. The control bar (status/Pause/Help/
		# Settings/Quit) is separate and always visible regardless.
		should_show = self.debug or control_state == 'Keyboard'
		if should_show != self._visible:
			if should_show:
				self.root.deiconify()
			else:
				self.root.withdraw()
			self._visible = should_show

		if not should_show:
			return

		c = self.canvas
		c.delete('all')

		if self.debug:
			c.create_text(
				16, 16, anchor='nw', fill='#ff5555',
				font=('Segoe UI', 14, 'bold'), text=event_text,
			)
			c.create_text(
				16, 40, anchor='nw', fill='#ff5555',
				font=('Segoe UI', 14, 'bold'), text=control_state,
			)
			c.create_text(
				16, 64, anchor='nw', fill='#ff5555',
				font=('Segoe UI', 14, 'bold'),
				text=f'Sensitivity: {self.mouse_sensitivity}x',
			)

		if control_state == 'Keyboard':
			for button in button_list:
				x, y = button.pos
				w, h = button.size
				fill = _STATE_COLORS.get(button.color, _STATE_COLORS['idle'])
				c.create_rectangle(
					x, y, x + w, y + h, fill=fill, outline='#666666', width=1.5,
				)

				# Single letter keys flip visible case with Shift/Caps, like
				# a phone keyboard -- everything else (digits, symbols,
				# multi-character utility labels) is unaffected, since only
				# letters have an upper/lower form at all.
				label = button.text
				if len(label) == 1 and label.isalpha():
					label = label.upper() if shift_active else label.lower()

				# Two-word labels that are narrow relative to their text
				# ('Copy Typed', 'Cut Typed') are split onto their own
				# centered line each, rather than relying on create_text's
				# auto-wrap -- its default justify is 'left', which
				# left-aligns wrapped lines within the (centered) text
				# block instead of centering each line, and auto-wrap's
				# line breaks depend on a width estimate that doesn't
				# always land where you'd want it to. 'Select All' is wide
				# enough to just fit on one line, so it's left alone rather
				# than force-split into two cramped, overlapping lines.
				if button.text in _TWO_LINE_LABELS:
					display_text = label.replace(' ', '\n', 1)
				else:
					display_text = label

				# Space's button is wide/obvious enough on its own not to
				# need a label at all.
				if button.text == 'Space':
					continue

				# Only a true single character (a letter, digit, or symbol)
				# gets the larger size -- it's the only case with just one
				# glyph and tons of spare room in the button. Every label
				# with more than one character, whether it wraps onto two
				# lines ('Copy Typed') or stays on one ('Shift', 'Clear',
				# '123') is back to the original smaller size: at the
				# larger size those multi-character labels looked
				# oversized/cramped against their own buttons, which is
				# what this reverts.
				if len(button.text) == 1:
					font_size = max(10, min(20, int(h / 2.2)))
				elif button.text in _EMPHASIZED_LABELS:
					font_size = max(9, min(16, int(h / 3.2)))
				else:
					font_size = max(7, min(13, int(h / 4.5)))

				c.create_text(
					x + w / 2, y + h / 2, fill='white',
					anchor='center', justify='center',
					font=('Arial', font_size), text=display_text,
				)

		c.create_text(
			16, self.panel_height - 24, anchor='nw', fill='#55ff55',
			font=('Segoe UI', 12), text=typed_preview,
		)
