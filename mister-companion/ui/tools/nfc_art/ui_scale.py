from PyQt6.QtCore import QSize


def scale(value):
    return int(value)


def scaled_size(width, height):
    return QSize(scale(width), scale(height))

