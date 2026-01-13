"""
SceneRenderer - Serviço responsável por renderizar elementos visuais e overlays.

Este serviço encapsula toda a lógica relacionada a:
- Criação de elementos visuais (imagens, textos, gifs, etc.)
- Layout e posicionamento de elementos usando LayoutEngine
- Aplicação de overlays sobre backgrounds
- Composição final de elementos visuais

Preserva o comportamento exato do UnifiedVideoEngine original em termos de:
- force_rgb aplicado a todos os clips
- Tamanhos e posições calculados pelo LayoutEngine
- Ordem de composição dos elementos
- Fallback para posicionamento centralizado
"""

from moviepy.editor import CompositeVideoClip
from libs.VisualClip import VisualClip, force_rgb
from libs.LayoutEngine import LayoutEngine
from libs.OverlayEngine import OverlayEngine


def deep_merge(a, b):
    """Mescla dicionários recursivamente."""
    if not isinstance(a, dict):
        return b
    result = dict(a)
    for k, v in (b or {}).items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


class SceneRenderer:
    """
    Renderizador de elementos visuais e overlays.
    
    Responsável por criar e compor elementos visuais da cena,
    incluindo overlays sobre backgrounds.
    """
    
    def __init__(self, resolution_output=(1080, 1920), config_instance=None, global_settings=None):
        """
        Inicializa o renderizador de cena.
        
        Args:
            resolution_output: Tupla (width, height) para resolução do vídeo
            config_instance: Instância de Config para paddings e configurações
            global_settings: Configurações globais (overlays, etc.)
        """
        self.resolution_output = resolution_output
        self.config_instance = config_instance
        self.global_settings = global_settings or {}
    
    def create_visuals(self, visual_elements, scene_duration, scene_dir):
        """
        Cria clip com elementos visuais da cena.
        
        Args:
            visual_elements: Lista de elementos visuais a renderizar
            scene_duration: Duração da cena em segundos
            scene_dir: Diretório temporário da cena
        
        Returns:
            CompositeVideoClip com elementos ou None se falhar
        """
        if not visual_elements:
            return None
        
        print(f"[SceneRenderer] Processando {len(visual_elements)} elementos visuais...")
        
        valid_clips_info = []
        valid_element_data_for_layout = []
        
        # Gerar cada elemento visual
        for i, element_data in enumerate(visual_elements):
            try:
                config = {
                    "element_data": element_data,
                    "resolution_output": self.resolution_output,
                    "temp_dir": scene_dir,
                    "duration": scene_duration,
                }
                
                processor = VisualClip(config)
                raw_clip = processor.generate()
                
                if raw_clip:
                    w, h = raw_clip.size
                    element_data_copy = element_data.copy()
                    element_data_copy['original_size'] = (w, h)
                    
                    valid_clips_info.append(raw_clip)
                    valid_element_data_for_layout.append(element_data_copy)
                    print(f"[SceneRenderer] ✅ Elemento {i + 1} gerado: {w}x{h}")
                else:
                    print(f"[SceneRenderer] ⚠️ Falha ao gerar elemento {i + 1}")
            
            except Exception as e:
                print(f"[SceneRenderer] ❌ Erro no elemento {i + 1}: {e}")
        
        if not valid_clips_info:
            print("[SceneRenderer] ❌ Nenhum elemento visual foi gerado com sucesso")
            return None
        
        # Aplicar layout
        try:
            layout_results = LayoutEngine.process_stack_layout(
                valid_element_data_for_layout,
                self.config_instance
            )
            
            final_clips = []
            
            for i, clip in enumerate(valid_clips_info):
                if i >= len(layout_results):
                    break
                
                layout = layout_results[i]
                final_size = layout['final_size']
                final_pos = layout['final_position']
                
                try:
                    clip_resized = clip.resize(newsize=final_size)
                    clip_positioned = clip_resized.set_position(final_pos)
                    final_clips.append(clip_positioned)
                    print(f"[SceneRenderer] ✅ Elemento {i + 1} posicionado: {final_size} @ {final_pos}")
                except Exception as e:
                    print(f"[SceneRenderer] ❌ Falha ao posicionar elemento {i + 1}: {e}")
            
            if not final_clips:
                print("[SceneRenderer] ❌ Nenhum elemento foi posicionado corretamente")
                return None
            
            return CompositeVideoClip(final_clips, size=self.resolution_output).set_duration(
                scene_duration).fl_image(force_rgb)
        
        except Exception as e:
            print(f"[SceneRenderer] ❌ Falha no LayoutEngine: {e}")
            print("[SceneRenderer] Usando posicionamento centralizado como fallback")
            
            # Fallback para centralizado
            centered_clips = []
            for i, clip in enumerate(valid_clips_info):
                try:
                    clip_centered = clip.set_position('center')
                    centered_clips.append(clip_centered)
                except Exception as e:
                    print(f"[SceneRenderer] ❌ Falha no fallback do elemento {i + 1}: {e}")
            
            if centered_clips:
                return CompositeVideoClip(centered_clips, size=self.resolution_output).set_duration(
                    scene_duration).fl_image(force_rgb)
            
            return None
    
    def apply_overlays(self, background_clip, scene_data, scene_duration):
        """
        Aplica overlays ao background.
        
        Args:
            background_clip: Clip de background base
            scene_data: Dados da cena (para overlays específicos)
            scene_duration: Duração da cena em segundos
        
        Returns:
            Clip composto com overlays ou background original se falhar
        """
        global_overlays = self.global_settings.get("overlays", {}) or {}
        scene_overlays = scene_data.get("overlays", None)
        
        # Merge de configurações
        if scene_overlays is not None:
            overlays_config = deep_merge(global_overlays, scene_overlays)
        else:
            overlays_config = dict(global_overlays)
        
        overlay_clip = None
        if overlays_config:
            try:
                print("[SceneRenderer] Processando overlays...")
                ov_engine = OverlayEngine(resolution=self.resolution_output)
                overlay_clip = ov_engine.create_overlays_clip(overlays_config, scene_duration)
            except Exception as e:
                print(f"[SceneRenderer] ⚠️ Falha ao gerar overlays: {e}")
        
        if overlay_clip is not None:
            try:
                print("[SceneRenderer] Compondo fundo + overlays")
                composed = CompositeVideoClip([background_clip, overlay_clip],
                                            size=self.resolution_output).set_duration(scene_duration)
                return composed.fl_image(force_rgb)
            except Exception as e:
                print(f"[SceneRenderer] ❌ Falha ao compor overlay sobre fundo: {e}")
        
        return background_clip.fl_image(force_rgb)
