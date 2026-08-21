
import os
import time
import urllib.request

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
	HandLandmarker,
	HandLandmarkerOptions,
	RunningMode,
)
import numpy as np
from collections import deque

from mouse_control import execute_event_fast
from event_classifier import get_event_fast
import constants as c
import keyboard as k

import pyperclip


MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hand_landmarker.task')
MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'


def ensure_model_downloaded(model_path=MODEL_PATH, model_url=MODEL_URL):
	"""Download the HandLandmarker task model if it isn't already on disk."""
	if not os.path.exists(model_path):
		print(f'Downloading hand landmarker model to {model_path}...')
		urllib.request.urlretrieve(model_url, model_path)
	return model_path


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
	# NOTE: `landmarks` is a plain list of NormalizedLandmark objects, as
	# returned per-hand by the HandLandmarker Tasks API (no `.landmark`
	# wrapper like the old `mp.solutions.hands` API used).
	for landmark in landmarks:
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

	min_detection_confidence = 0.7
	min_tracking_confidence = 0.5

	# Camera

	cap = cv2.VideoCapture(0)
	cap.set(cv2.CAP_PROP_FRAME_WIDTH, cap_width)
	cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cap_height)

	model_path = ensure_model_downloaded()

	base_options = BaseOptions(model_asset_path=model_path)
	options = HandLandmarkerOptions(
		base_options=base_options,
		running_mode=RunningMode.VIDEO,
		num_hands=1,
		min_hand_detection_confidence=min_detection_confidence,
		min_hand_presence_confidence=min_detection_confidence,
		min_tracking_confidence=min_tracking_confidence,
	)
	landmarker = HandLandmarker.create_from_options(options)

	# detect_for_video requires monotonically increasing timestamps.
	start_time_ms = int(time.time() * 1000)

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

		mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image)
		timestamp_ms = int(time.time() * 1000) - start_time_ms
		results = landmarker.detect_for_video(mp_image, timestamp_ms)

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

		if results.hand_landmarks:
			for hand_landmarks, handedness in zip(results.hand_landmarks, results.handedness):

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
	landmarker.close()




if __name__ == '__main__':
	main()


