

import cv2
import pyautogui



class Button():
	def __init__(self, pos, text, size=[85, 85]):
		self.pos = pos
		self.size = size
		self.text = text
		self.color = (0, 0, 0)



def draw(img, buttonList, control_state):

	if control_state == 'Keyboard':
		for button in buttonList:
			x, y = button.pos
			w, h = button.size
			color = button.color
			#cvzone.cornerRect(img, (button.pos[0], button.pos[1],
			#	button.size[0],button.size[0]), 20 ,rt=0)
			cv2.rectangle(img, button.pos, (int(x + w), int(y + h)), (255, 144, 30), cv2.FILLED)
			cv2.putText(img, button.text, (x + 20, y + 65),
				cv2.FONT_HERSHEY_PLAIN, 4, color, 4)
	return img



def get_button_list():

	keyboard_keys = [
				['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '<'],
				["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
				["A", "S", "D", "F", "G", "H", "J", "K", "L", ";"],
				["Z", "X", "C", "V", "B", "N", "M", ",", ".", "/"],
				[' ']
				]

	buttonList = []
	# mybutton = Button([100, 100], "Q")
	for k in range(len(keyboard_keys)):

		# Offset every other row of keys
		if k % 2 == 1:
			x_offset = 55
		else:
			x_offset = 0


		for x, key in enumerate(keyboard_keys[k]):
			b = Button([100 * x + 25 + x_offset, 100 * k + 50], key)

			# Special case for space
			if b.text == ' ':
				b.size = [425, 85]
				b.pos[0] += 85*2

			buttonList.append(b)

	return buttonList


def execute_event_keyboard(event, abs_landmark_list, button_list):

	curr_mouse_x, curr_mouse_y = pyautogui.position()

	typed_char = None
	### Detect if mouse over key

	for button in button_list:
		x, y = button.pos
		w, h = button.size

		if curr_mouse_x > x and curr_mouse_x < x + w:
			if curr_mouse_y - 50 > y and curr_mouse_y - 50 < y + h:

				# Button found

				if event == 'Mousing':
					button.color = (0, 255, 0)
				elif event == 'Left-Click':
					#print(f'Mouse Position: {curr_mouse_x}, {curr_mouse_y}.')
					#print(f'Key {button.text} Position: {button.pos}.')
					button.color = (255, 0, 0)
					typed_char = button.text
					print(button.text)
			else:
				button.color = (0, 0, 0)
		else:
			button.color = (0, 0, 0)

	return button_list, typed_char



