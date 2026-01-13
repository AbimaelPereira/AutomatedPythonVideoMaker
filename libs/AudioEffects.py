"""
AudioEffects - Biblioteca de processamento de áudio com efeitos
"""
import os
import hashlib
from pydub import AudioSegment
import numpy as np
from scipy import signal


class AudioEffects:
    """
    Classe para aplicar efeitos de áudio. 
    Estrutura similar às libs existentes (BackgroundVideo, VisualClip).
    """
    
    # Cache de áudios processados
    _cache = {}
    
    def __init__(self, params=None):
        defaults = {
            "audio_path": None,
            "output_dir": None,
        }
        if params:
            defaults.update(params)
        for k, v in defaults.items():
            setattr(self, k, v)
        
        self._audio = None
        if self.audio_path and os.path.exists(self.audio_path):
            self._audio = AudioSegment.from_file(self.audio_path)
    
    def load(self, audio_path:  str) -> "AudioEffects":
        """Carrega um arquivo de áudio."""
        self.audio_path = audio_path
        self._audio = AudioSegment.from_file(audio_path)
        return self
    
    def apply_reverb(
        self,
        dry:  int = 70,
        wet: int = 30,
        decay: float = 0.5,
        room_size: float = 0.5,
        low_cut: int = 200
    ) -> "AudioEffects":
        """
        Aplica reverb ao áudio.
        
        Args:
            dry: 0-100, volume do áudio original
            wet: 0-100, volume do reverb
            decay: 0.0-1.0, tempo de decaimento
            room_size: 0.0-1.0, tamanho do ambiente (afeta delay e densidade)
            low_cut: frequência em Hz para corte de graves no reverb
        
        Returns:
            self para encadeamento
        """
        if self._audio is None:
            raise ValueError("Nenhum áudio carregado")
        
        # Normaliza parâmetros
        dry = max(0, min(100, dry)) / 100.0
        wet = max(0, min(100, wet)) / 100.0
        decay = max(0.1, min(1.0, decay))
        room_size = max(0.1, min(1.0, room_size))
        
        # Converte para array numpy
        samples = np.array(self._audio.get_array_of_samples(), dtype=np.float32)
        sample_rate = self._audio.frame_rate
        channels = self._audio.channels
        
        if channels == 2:
            samples = samples.reshape((-1, 2))
        
        # Aplica high-pass filter no sinal wet (low_cut)
        if low_cut > 0:
            nyquist = sample_rate / 2
            normalized_cutoff = min(low_cut / nyquist, 0.99)
            b, a = signal.butter(2, normalized_cutoff, btype='high')
            if channels == 2:
                samples_filtered = np.column_stack([
                    signal.filtfilt(b, a, samples[: , 0]),
                    signal.filtfilt(b, a, samples[:, 1])
                ])
            else:
                samples_filtered = signal.filtfilt(b, a, samples)
        else:
            samples_filtered = samples.copy()
        
        # Gera impulse response simples baseado em room_size e decay
        ir_duration = int(sample_rate * room_size * 2)  # até 2s para room_size=1.0
        ir = self._generate_impulse_response(ir_duration, decay, sample_rate)
        
        # Convolução para reverb
        if channels == 2:
            reverb_left = signal.fftconvolve(samples_filtered[: , 0], ir, mode='full')[:len(samples)]
            reverb_right = signal.fftconvolve(samples_filtered[:, 1], ir, mode='full')[:len(samples)]
            reverb_signal = np.column_stack([reverb_left, reverb_right])
        else:
            reverb_signal = signal.fftconvolve(samples_filtered, ir, mode='full')[:len(samples)]
        
        # Normaliza reverb
        max_val = np.max(np.abs(reverb_signal))
        if max_val > 0:
            reverb_signal = reverb_signal / max_val * np.max(np.abs(samples))
        
        # Mix dry/wet
        mixed = (samples * dry + reverb_signal * wet).astype(np.int16)
        
        # Reconstrói AudioSegment
        if channels == 2:
            mixed = mixed.flatten()
        
        self._audio = AudioSegment(
            data=mixed.tobytes(),
            sample_width=2,
            frame_rate=sample_rate,
            channels=channels
        )
        
        return self
    
    def _generate_impulse_response(self, length: int, decay: float, sample_rate: int) -> np.ndarray:
        """Gera impulse response exponencial simples."""
        t = np.linspace(0, length / sample_rate, length)
        ir = np.random.randn(length) * np.exp(-t / (decay * 0.5))
        # Normaliza
        ir = ir / np.max(np.abs(ir))
        return ir.astype(np.float32)
    
    def export(self, output_path: str, format: str = "mp3") -> str:
        """Exporta o áudio processado."""
        if self._audio is None:
            raise ValueError("Nenhum áudio carregado")
        
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        self._audio.export(output_path, format=format)
        return output_path
    
    def get_audio_segment(self) -> AudioSegment:
        """Retorna o AudioSegment atual."""
        return self._audio
    
    def get_duration(self) -> float:
        """Retorna duração em segundos."""
        if self._audio is None:
            return 0.0
        return len(self._audio) / 1000.0
    
    @classmethod
    def get_cached_or_process(
        cls,
        audio_path: str,
        output_dir: str,
        reverb_params: dict = None
    ) -> str:
        """
        Retorna caminho do áudio processado, usando cache se disponível.
        
        Args:
            audio_path: caminho do áudio original
            output_dir: diretório de saída
            reverb_params: parâmetros do reverb (se None, não aplica reverb)
        
        Returns:
            Caminho do arquivo processado
        """
        # Gera cache key
        cache_data = {
            "path": audio_path,
            "mtime": os.path.getmtime(audio_path) if os.path.exists(audio_path) else 0,
            "reverb":  reverb_params
        }
        cache_key = hashlib.md5(str(cache_data).encode()).hexdigest()[:12]
        
        # Verifica cache em memória
        if cache_key in cls._cache and os.path.exists(cls._cache[cache_key]):
            return cls._cache[cache_key]
        
        # Verifica cache em disco
        basename = os.path.splitext(os.path.basename(audio_path))[0]
        cached_path = os.path.join(output_dir, f"{basename}_fx_{cache_key}.mp3")
        
        if os.path.exists(cached_path):
            cls._cache[cache_key] = cached_path
            return cached_path
        
        # Processa
        processor = cls({"audio_path": audio_path, "output_dir": output_dir})
        
        if reverb_params:
            processor.apply_reverb(**reverb_params)
        
        processor.export(cached_path)
        cls._cache[cache_key] = cached_path
        
        return cached_path