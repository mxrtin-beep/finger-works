"""The fullscreen canvas window the two artistic modes draw on."""

import colorsys
import tkinter as tk

import art_gestures as ag
from overlay import _make_window_noactivate


# Same landmark connections main_fast.py traces in debug mode.
_HAND_CONNECTIONS = [
	(0, 1), (1, 2), (2, 3), (3, 4),
	(0, 5), (5, 6), (6, 7), (7, 8),
	(5, 9), (9, 10), (10, 11), (11, 12),
	(9, 13), (13, 14), (14, 15), (15, 16),
	(13, 17), (17, 18), (18, 19), (19, 20),
	(0, 17),
]


def hsv_hex(h, s, v):
	"""HSV (each 0..1) -> '#rrggbb'."""
	r, g, b = colorsys.hsv_to_rgb(h % 1.0, min(max(s, 0.0), 1.0), min(max(v, 0.0), 1.0))
	return f'#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}'


def rgb_hex(rgb):
	return '#%02x%02x%02x' % tuple(int(min(max(v, 0), 255)) for v in rgb)


class ArtWindow:
	"""A borderless, always-on-top, screen-sized window with one Tk canvas.

	Created fresh when an artistic mode starts and destroyed when it
	ends. It never takes keyboard focus (same no-activate trick as the
	rest of the overlay) so it can't steal focus from whatever you were
	using, and the control bar is lifted back above it so Pause / Mode /
	Quit stay reachable with the real mouse -- in these modes the hands
	don't drive the OS cursor, so the real mouse is how you reach them.
	"""

	def __init__(self, overlay, bg='#000000'):
		self.overlay = overlay
		self.width = overlay.screen_width
		self.height = overlay.screen_height

		self.win = tk.Toplevel(overlay.root)
		self.win.title('finger-works -- canvas')
		self.win.overrideredirect(True)
		self.win.attributes('-topmost', True)
		self.win.geometry(f'{self.width}x{self.height}+0+0')
		self.win.configure(bg=bg)
		self.win.bind('<Escape>', lambda _event: overlay._quit())
		self.win.protocol('WM_DELETE_WINDOW', overlay._quit)

		self.canvas = tk.Canvas(
			self.win, width=self.width, height=self.height, bg=bg, highlightthickness=0,
		)
		self.canvas.pack(fill='both', expand=True)

		self.win.update_idletasks()
		_make_window_noactivate(self.win.winfo_id())
		overlay.raise_controls()

	def close(self):
		try:
			self.win.destroy()
		except tk.TclError:
			pass

	def draw_ghost_hands(self, hands, tag='hud', right_color='#3d6a8f', left_color='#8f3d7a'):
		"""Faint skeletons of the tracked hands, mapped to screen space the
		same way the pointer is. With no real cursor to follow, this is
		how you see where your hands are relative to the canvas."""
		c = self.canvas
		for hand in hands:
			color = left_color if hand.label == 'Left' else right_color
			pts = [
				ag.frame_to_screen(p[0], p[1], hand.frame_w, hand.frame_h, self.width, self.height)
				for p in hand.abs
			]
			for a, b in _HAND_CONNECTIONS:
				c.create_line(pts[a][0], pts[a][1], pts[b][0], pts[b][1], fill=color, width=2, tags=tag)
			for x, y in pts:
				c.create_oval(x - 3, y - 3, x + 3, y + 3, fill=color, outline='', tags=tag)

	def draw_banner(self, text, y=None, color='#e67e22', tag='hud'):
		"""One centered line of status text (paused, no audio, ...)."""
		y = self.height * 0.5 if y is None else y
		self.canvas.create_text(
			self.width / 2, y, text=text, fill=color,
			font=('Segoe UI', 22, 'bold'), tags=tag,
		)
