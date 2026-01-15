import math
import numpy as np
from PIL import Image, ImageFilter
from moviepy.editor import ImageClip


class TransitionUtils:

    # -----------------------------
    # EASING
    # -----------------------------
    @staticmethod
    def ease_in_cubic(t):
        return t ** 3

    @staticmethod
    def ease_out_cubic(t):
        return 1 - (1 - t) ** 3

    @staticmethod
    def ease_in_out_sine(t):
        return -(math.cos(math.pi * t) - 1) / 2

    # -----------------------------
    # SHAKE FÍSICO (COM CORTE)
    # -----------------------------
    @staticmethod
    def damped_shake(t, amp, freq, decay, max_time):
        if t <= 0 or t > max_time:
            return 0
        return amp * math.sin(t * freq) * math.exp(-decay * t)

    # -----------------------------
    # BACKDROP BORRADO
    # -----------------------------
    @staticmethod
    def create_blurred_backdrop(frame, width, height, blur_radius, duration):
        pil_img = Image.fromarray(frame)
        pil_img = pil_img.resize((width, height), Image.LANCZOS)
        blurred = pil_img.filter(ImageFilter.GaussianBlur(blur_radius))
        return ImageClip(np.array(blurred)).set_duration(duration)
