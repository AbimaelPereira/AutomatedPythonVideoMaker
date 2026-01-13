"""
SceneAudioManager - Gerencia áudios de cena (narração + efeito de transição)
NOTA: Áudio de fundo (background.audio) é aplicado no vídeo final, não por cena. 
"""
import os
import random
import hashlib
from moviepy.editor import AudioFileClip, CompositeAudioClip
from libs.AudioEffects import AudioEffects


class SceneAudioManager: 
    """
    Gerencia a mixagem de áudios da cena: 
    - Narração
    - Efeito de transição (início da cena, paralelo à narração)
    
    NOTA: background.audio é tratado separadamente no vídeo final concatenado.
    """
    
    _effect_cache = {}
    _last_effect_used = None
    
    # Configuração fixa de reverb para efeitos de transição
    EFFECT_REVERB_PARAMS = {
        "dry":  60,
        "wet": 40,
        "decay": 0.4,
        "room_size":  0.3,
        "low_cut":  300
    }
    
    VALID_AUDIO_EXTENSIONS = [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"]
    
    def __init__(self, params=None):
        defaults = {
            "scene_duration": 0.0,
            "output_dir": None,
        }
        if params:
            defaults.update(params)
        for k, v in defaults.items():
            setattr(self, k, v)
    
    def create_scene_audio(
        self,
        narration_clip=None,
        transition_effect_config:  dict = None,
        scene_duration: float = None
    ):
        """
        Cria o áudio composto da cena (narração + efeito de transição).
        
        Args:
            narration_clip: AudioFileClip da narração (ou None)
            transition_effect_config: dict com configuração de efeito de transição
            scene_duration:  duração da cena em segundos
        
        Returns:
            CompositeAudioClip ou AudioFileClip ou None
        """
        duration = scene_duration or self.scene_duration
        audio_clips = []
        
        # 1. Narração
        if narration_clip:
            audio_clips.append(narration_clip)
        
        # 2. Efeito de transição (no início da cena)
        effect_audio = self._process_transition_effect(transition_effect_config, duration)
        if effect_audio:
            audio_clips.append(effect_audio)
        
        if not audio_clips:
            return None
        
        if len(audio_clips) == 1:
            return audio_clips[0]
        
        return CompositeAudioClip(audio_clips)
    
    def _process_transition_effect(self, config: dict, scene_duration: float):
        """Processa efeito de transição com reverb fixo e cache."""
        if not config:
            return None
        
        effect_type = config.get("type", "file")
        source = config.get("source")
        volume = config.get("volume", 1.0)
        
        if not source:
            return None
        
        try:
            # Seleciona arquivo de efeito
            if effect_type == "directory":
                audio_path = self._select_effect_from_directory(source)
            else:  # file
                audio_path = source
            
            if not audio_path or not os.path.exists(audio_path):
                print(f"[SceneAudio] Efeito de transição não encontrado: {audio_path}")
                return None
            
            # Processa com reverb (usa cache)
            processed_path = self._get_processed_effect(audio_path)
            
            if not processed_path:
                return None
            
            # Carrega e configura
            effect_clip = AudioFileClip(processed_path)
            
            # Duração original do efeito (não faz loop)
            if effect_clip.duration > scene_duration:
                effect_clip = effect_clip.subclip(0, scene_duration)
            
            effect_clip = effect_clip.volumex(volume)
            effect_clip = effect_clip.set_start(0)  # Início da cena
            
            print(f"[SceneAudio] ✅ Efeito de transição:  {os.path.basename(audio_path)} ({effect_clip.duration:.2f}s)")
            return effect_clip
            
        except Exception as e: 
            print(f"[SceneAudio] ❌ Erro ao processar efeito de transição: {e}")
            return None
    
    def _select_effect_from_directory(self, directory:  str) -> str:
        """
        Seleciona efeito de um diretório, evitando repetição do anterior.
        Se houver apenas um arquivo, repete. 
        """
        if not os.path.isdir(directory):
            return None
        
        files = [
            os.path.join(directory, f) for f in os.listdir(directory)
            if os.path.splitext(f.lower())[1] in self.VALID_AUDIO_EXTENSIONS
        ]
        
        if not files:
            return None
        
        if len(files) == 1:
            selected = files[0]
        else: 
            # Evita repetir o último usado
            available = [f for f in files if f != SceneAudioManager._last_effect_used]
            if not available:
                available = files
            selected = random.choice(available)
        
        SceneAudioManager._last_effect_used = selected
        return selected
    
    def _get_processed_effect(self, audio_path: str) -> str:
        """Retorna caminho do efeito processado com reverb (usa cache)."""
        cache_key = hashlib.md5(audio_path.encode()).hexdigest()[:12]
        
        if cache_key in SceneAudioManager._effect_cache:
            cached = SceneAudioManager._effect_cache[cache_key]
            if os.path.exists(cached):
                return cached
        
        output_dir = self.output_dir or os.path.dirname(audio_path)
        os.makedirs(output_dir, exist_ok=True)
        
        basename = os.path.splitext(os.path.basename(audio_path))[0]
        output_path = os.path.join(output_dir, f"{basename}_reverb_{cache_key}.mp3")
        
        if os.path.exists(output_path):
            SceneAudioManager._effect_cache[cache_key] = output_path
            return output_path
        
        return output_path
        
        # try:
        #     processor = AudioEffects({"audio_path": audio_path})
        #     processor.apply_reverb(**self.EFFECT_REVERB_PARAMS)
        #     processor.export(output_path)
            
        #     SceneAudioManager._effect_cache[cache_key] = output_path
        #     print(f"[SceneAudio] Efeito processado com reverb: {output_path}")
        #     return output_path
            
        # except Exception as e:
        #     print(f"[SceneAudio] ❌ Erro ao processar reverb do efeito: {e}")
        #     return audio_path  # Fallback:  usa original