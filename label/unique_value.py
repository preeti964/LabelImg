
import os, sys
import cv2
import numpy as np

#img=cv2.imread('img0026_2020-03-27_164339_617_seg.png',0)
img=cv2.imread('demo_seg.png',0)
print(img)
print(np.min(img))
print(np.max(img))
print("Uniques values are:")
print(np.unique(img))

