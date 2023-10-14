
import cv2
import mediapipe as mp
import numpy as np
from collections import deque

from mouse_control import execute_event_fast
from event_classifier import get_event_fast
import constants as c
import keyboard as k

import pyperclip


device = 0
width = 1440
height = 900

font = cv2.FONT_HERSHEY_SIMPLEX
org = (00, 185)
fontScale = 1
color = (0, 0, 255)
thickness = 2

play_audio = False
history_length = 8
event_history = deque(maxlen=history_length)


def calc_landmark_list(image, landmarks):
	image_width, image_height = image.shape[1], image.shape[0]

	landmark_point = []

	# Keypoint
	for _, landmark in enumerate(landmarks.landmark):
		landmark_x = min(int(landmark.x * image_width), image_width - 1)
		landmark_y = min(int(landmark.y * image_height), image_height - 1)
		landmark_z = landmark.z

		landmark_point.append([landmark_x, landmark_y, landmark_z])

	return landmark_point



def pre_process_landmark(landmark_list):

	base_x, base_y = landmark_list[0][0], landmark_list[0][1]

	for i in range(len(landmark_list)):
		landmark_list[i][0] -= base_x
		landmark_list[i][1] -= base_y

	#maxval = max(max(x) for x in landmark_list)
	#minval = min(min(x) for x in landmark_list)

	#max_value = float(max(maxval, -minval))
	max_value = 1

	for i in range(len(landmark_list)):
		landmark_list[i][0] = float(landmark_list[i][0]) / max_value
		landmark_list[i][1] = float(landmark_list[i][1]) / max_value
	return landmark_list



def main():

	cap_device = device
	cap_width = width
	cap_height = height

	use_static_image_mode = True
	min_detection_confidence = 0.7
	min_tracking_confidence = 0.5

	# Camera

	cap = cv2.VideoCapture(0)
	cap.set(cv2.CAP_PROP_FRAME_WIDTH, cap_width)
	cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cap_height)

	mp_hands = mp.solutions.hands
	hands = mp_hands.Hands(
		static_image_mode=use_static_image_mode,
		max_num_hands=1,
		min_detection_confidence=min_detection_confidence,
		min_tracking_confidence=min_tracking_confidence,
	)

	mode = 0

	event = ''

	button_list = k.get_button_list()

	control_state = 'Mouse'	# Mouse or Keyboard

	typed_text = '>'

	while event != 'Quit':

		key = cv2.waitKey(10)
		if key == 27:  # ESC
			break

		ret, image = cap.read()
		if not ret:
			break
		image = cv2.flip(image, 1)  # Mirror display

		image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

		results = hands.process(image)

		image = k.draw(image, button_list, control_state)

		# EVENT TEXT
		image = cv2.putText(image, event, (50, 50), font, 
			fontScale, color, thickness, cv2.LINE_AA)

		# CONTROL STATE TEXT
		image = cv2.putText(image, control_state, (50, 100), font, 
			fontScale, color, thickness, cv2.LINE_AA)

		# TYPED TEXT
		image = cv2.putText(image, typed_text, (50, 600), font, 
			fontScale, color, thickness, cv2.LINE_AA)

		if results.multi_hand_landmarks is not None:
			for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):

				abs_landmark_list = calc_landmark_list(image, hand_landmarks)
				rel_landmark_list = pre_process_landmark(abs_landmark_list)

				abs_landmark_list = np.array(abs_landmark_list)
				rel_landmark_list = np.array(rel_landmark_list)

				x, y, z = rel_landmark_list[c.INDEX_IDX]
				#print(x, y, z)

				#abs_point_history.append(abs_landmark_list)

				event = get_event_fast(abs_landmark_list, rel_landmark_list, control_state)

				event_history.append(event)

				if event == 'Keyboard On':
					control_state = 'Keyboard'
				elif event == 'Keyboard Off':
					control_state = 'Mouse'

				

				if control_state == 'Keyboard':
					button_list, typed_char = k.execute_event_keyboard(event, abs_landmark_list, button_list)
					image = k.draw(image, button_list, control_state)

					if typed_char is not None:

						if typed_char not in c.SPECIAL_KEYS:
							typed_text += typed_char

							if play_audio:
								k.say_key_pressed(typed_char)
						elif typed_char == '<':
							typed_text = typed_text[:-1]							
						elif typed_char == 'Clear':
							typed_text = ''
						elif typed_char == 'Space':
							typed_text += ' '
						print('In clipboard: ', typed_text)
						pyperclip.copy(typed_text)

				execute_event_fast(event, abs_landmark_list, event_history)
		
		cv2.imshow('Video', image)

	cap.release()
	cv2.destroyAllWindows()




if __name__ == '__main__':
	main()


