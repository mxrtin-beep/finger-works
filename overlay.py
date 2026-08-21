
import sys
import tkinter as tk


# Maps a button's logical state (set by keyboard.execute_event_keyboard) to
# a fill color for drawing. Kept as plain state names rather than raw color
# tuples so keyboard.py doesn't need to know anything about how it's drawn.
_STATE_COLORS = {
	'idle': '#3a3a3a',
	'hover': '#2ecc71',
	'active': '#e74c3c',
}


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


class Overlay:
	"""A fixed, always-on-top panel docked in the corner of the screen.

	Shows the current action/mode as text, and (in Keyboard mode) the
	on-screen keyboard -- all in real screen coordinates, the same space
	the OS mouse cursor lives in, so hit-testing a key against the real
	cursor position is a plain coordinate comparison, not a translation
	between two different coordinate spaces.
	"""

	def __init__(self, screen_width, screen_height, panel_width=None, panel_height=None, margin=20):
		self.screen_width = screen_width
		self.screen_height = screen_height

		self.panel_width = panel_width or int(screen_width * 0.42)
		self.panel_height = panel_height or int(screen_height * 0.34)

		self.origin_x = screen_width - self.panel_width - margin
		self.origin_y = screen_height - self.panel_height - margin

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
			highlightthickness=0,
		)
		self.canvas.pack(fill='both', expand=True)

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

	def draw(self, event_text, control_state, typed_preview, button_list):
		c = self.canvas
		c.delete('all')

		c.create_text(
			16, 16, anchor='nw', fill='#ff5555',
			font=('Segoe UI', 14, 'bold'), text=event_text,
		)
		c.create_text(
			16, 40, anchor='nw', fill='#ff5555',
			font=('Segoe UI', 14, 'bold'), text=control_state,
		)

		if control_state == 'Keyboard':
			for button in button_list:
				x, y = button.pos
				w, h = button.size
				fill = _STATE_COLORS.get(button.color, _STATE_COLORS['idle'])
				c.create_rectangle(x, y, x + w, y + h, fill=fill, outline='#555555')

				# Two-word labels ('Copy Typed', 'Cut Typed') are split onto
				# their own centered line each, rather than relying on
				# create_text's auto-wrap -- its default justify is 'left',
				# which left-aligns wrapped lines within the (centered) text
				# block instead of centering each line, and auto-wrap's
				# line breaks depend on a width estimate that doesn't always
				# land where you'd want it to.
				display_text = button.text.replace(' ', '\n', 1)
				font_size = max(8, int(h / 3))
				c.create_text(
					x + w / 2, y + h / 2, fill='white',
					anchor='center', justify='center',
					font=('Segoe UI', font_size), text=display_text,
				)

		c.create_text(
			16, self.panel_height - 24, anchor='nw', fill='#55ff55',
			font=('Segoe UI', 12), text=typed_preview,
		)
