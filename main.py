import os
import json
import time
from dotenv import load_dotenv
from libs.UnifiedVideoEngine import UnifiedVideoEngine

load_dotenv()

def main():
    print("\n" + "="*60)
    print("🎬 GERADOR DE VÍDEOS AUTOMATIZADO V3 (Unified)")
    print("="*60)
    
    start_time = time.time()
    
    # Seleção de JSON
    if os.getenv("DEBUG") == "1":
        json_file = os.getenv("DEFAULT_JSON_DEBUG", "video-spec-v3-doc.md") # Ajustar para seu json de teste
        print(f"🔧 Modo DEBUG ativado")
    else:
        json_file = input("\n📂 Informe o caminho do arquivo JSON V3: ").strip()
        if not json_file:
            json_file = "json_examples/default.json"

    if not os.path.exists(json_file):
        print(f"❌ Arquivo não encontrado: {json_file}")
        return

    # Carregar JSON
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            # Suporta tanto lista de vídeos quanto objeto único (transforma em lista)
            data = json.load(f)
            videos_config = data if isinstance(data, list) else [data]
    except Exception as e:
        print(f"❌ Erro ao ler JSON: {e}")
        return
    
    success_count = 0
    
    for index, video_config in enumerate(videos_config, 1):
        print(f"\n🎥 Processando Vídeo {index}/{len(videos_config)}")
        
        engine = UnifiedVideoEngine(video_config)
        if engine.process():
            success_count += 1
            print("✅ Vídeo concluído com sucesso!")
        else:
            print("❌ Falha ao gerar vídeo.")
            
    elapsed = time.time() - start_time
    print("\n" + "="*60)
    print(f"🏁 Fim. Sucesso: {success_count}/{len(videos_config)}. Tempo: {elapsed:.2f}s")
    print("="*60)

if __name__ == "__main__":
    main()