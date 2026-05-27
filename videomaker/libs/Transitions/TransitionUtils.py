import math
import numpy as np
from PIL import Image, ImageFilter
from moviepy.editor import ImageClip
from scipy.ndimage import gaussian_filter

class TransitionUtils:
    @staticmethod
    def ease_in_cubic(t):
        return t ** 3

    @staticmethod
    def ease_out_cubic(t):
        return 1 - (1 - t) ** 3

    @staticmethod
    def ease_in_out_sine(t):
        return -(math.cos(math.pi * t) - 1) / 2

    @staticmethod
    def damped_shake(t, amp, freq, decay, max_time):
        if t <= 0 or t > max_time:
            return 0
        return amp * math.sin(t * freq) * math.exp(-decay * t)

    @staticmethod
    def apply_gaussian_blur(frame, blur_radius):
        """
        Aplica blur gaussiano em um frame usando scipy.
        Args:
            frame: numpy array do frame
            blur_radius: intensidade do blur (0 = sem blur)
        Returns:
            frame com blur aplicado
        """
        if blur_radius <= 0:
            return frame
        
        # Garantir que seja uint8
        if frame.dtype != np.uint8:
            frame = frame.astype(np.uint8)
        
        # Converter para float para processamento
        frame_float = frame.astype(np.float32)
        
        # Aplicar blur em cada canal
        blurred = np.zeros_like(frame_float)
        for i in range(frame.shape[2] if len(frame.shape) > 2 else 1):
            if len(frame.shape) > 2:
                blurred[:, :, i] = gaussian_filter(frame_float[:, :, i], sigma=blur_radius)
            else:
                blurred = gaussian_filter(frame_float, sigma=blur_radius)
        
        # Converter de volta para uint8
        return np.clip(blurred, 0, 255).astype(np.uint8)

    @staticmethod
    def create_blurred_backdrop(frame, width, height, blur_radius, duration):
        # CORREÇÃO: Garantir que o frame seja uint8 (PIL não aceita int64 <i8)
        if frame.dtype != np.uint8:
            frame = frame.astype(np.uint8)
        
        # CORREÇÃO: Caso o frame venha com erro de renderização (1, 1, 3)
        if frame.shape[0] <= 1 or frame.shape[1] <= 1:
            frame = np.zeros((height, width, 3), dtype=np.uint8)

        pil_img = Image.fromarray(frame)
        pil_img = pil_img.resize((width, height), Image.LANCZOS)
        blurred = pil_img.filter(ImageFilter.GaussianBlur(blur_radius))
        return ImageClip(np.array(blurred)).set_duration(duration)