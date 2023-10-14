
import cv2
import torch
import mediapipe as mp
import numpy as np
from collections import deque

from event_classifier import get_event
from mouse_control import execute_event

'''
Things to do

Pointer (8) --> mouse
Index and thumb opening (4, 8) --> zoom in
Index and thumb closing (4, 8) --> zoom out

Index and middle swiping (8, 12) --> scroll
Whole hand swiping (4, 8, 12, 16, 20) --> swipe

Index and thumb touching briefly --> left click
Index, middle, and thumb touching briefly --> right click

Whole hand closing: minimize program?
'''


frameWidth = 640
frameHeight = 480
cap = cv2.VideoCapture(0) # 0: iphone; 1: mac webcam SOMETIMES
cap.set(3, frameWidth)
cap.set(4, frameHeight)
cap.set(10,150)

desired_fps = 60
original_fps = int(cap.get(cv2.CAP_PROP_FPS))
frame_skip_factor = int(original_fps / desired_fps)


font = cv2.FONT_HERSHEY_SIMPLEX
org = (00, 185)
fontScale = 1
color = (0, 0, 255)
thickness = 2



use_static_image_mode = True
min_detection_confidence = 0.7
min_tracking_confidence = 0.5

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
	static_image_mode=use_static_image_mode,
	max_num_hands=2,
	min_detection_confidence=min_detection_confidence,
	min_tracking_confidence=min_tracking_confidence,
)


history_length = 8
rel_point_history = deque(maxlen=history_length)
abs_point_history = deque(maxlen=history_length)

event_history_length = 4
event_history = deque(maxlen=event_history_length)

rel_landmark_velocities = np.empty((21, 2))
abs_landmark_velocities = np.empty((21, 2))

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



def dist(pos):
	x = pos[0]
	y = pos[1]
	return x**2 + y**2

def mode(data):
	# Use numpy.unique to get unique values and their counts
	unique_values, counts = np.unique(data, return_counts=True)

	# Find the index with the maximum count
	max_count_index = np.argmax(counts)

	# The mode is the unique value with the maximum count
	mode = unique_values[max_count_index]

	return mode


true_event = ''
while true_event != 'Quit':

	success, img = cap.read()
	img = cv2.flip(img, 1)  # Mirror display

	debug_image = np.copy(img)
	#cv2.imshow("Result", img)

	# Q to quit
	if cv2.waitKey(1) & 0xFF == ord('q'):
		break

	for _ in range(frame_skip_factor - 1):
		ret = cap.grab()  # Skip frames


	img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)	# BGR to RGB

	results = hands.process(img)

	#img = torch.from_numpy(img)		# to torch
	#print(f'Shape: {img.shape}')


	if results.multi_hand_landmarks is not None:
		for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):

			# print(hand_landmarks)  # XYZ coordinates

			abs_landmark_list = calc_landmark_list(img, hand_landmarks)
			rel_landmark_list = pre_process_landmark(abs_landmark_list)

			z = round(abs_landmark_list[8][2], 2)

			abs_landmark_list = np.array(abs_landmark_list)
			rel_landmark_list = np.array(rel_landmark_list)

			abs_point_history.append(abs_landmark_list)
			rel_point_history.append(rel_landmark_list)

			abs_landmark_velocities = np.array(list(abs_point_history))[-1, :, :] - np.array(list(abs_point_history))[0, :, :]
			abs_landmark_velocities = abs_landmark_velocities.astype('float64') / float(history_length)

			rel_landmark_velocities = np.array(list(rel_point_history))[-1, :, :] - np.array(list(rel_point_history))[0, :, :]
			rel_landmark_velocities = rel_landmark_velocities.astype('float64') / float(history_length)


			debug_image = cv2.putText(debug_image, true_event+str(z), (50, 50), font, 
                   fontScale, color, thickness, cv2.LINE_AA)

			#print(rel_landmark_list[4], rel_landmark_list[8], rel_landmark_list[12], rel_landmark_list[16], rel_landmark_list[20])

			curr_event = get_event(abs_landmark_list, rel_landmark_list, abs_landmark_velocities, rel_landmark_velocities)
			
			#event_history.append(curr_event)

			#true_event = mode(event_history)
			true_event = curr_event
			print(true_event)

			execute_event(true_event, abs_landmark_list, rel_landmark_list, abs_landmark_velocities, rel_landmark_velocities)

	cv2.imshow("Result", debug_image)



cap.release()
cv2.destroyAllWindows()


