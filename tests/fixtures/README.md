# Face detection fixture

`astronaut.png` is the standard scikit-image example image, obtained from the official tagged source:
https://github.com/scikit-image/scikit-image/blob/v0.19.0/skimage/data/astronaut.png

It is used only to test face localization, crop bounds, and image rendering. Tests do not identify the person or infer personal attributes. Other tests use generated geometric images and mocked detector boxes.
