import os
import json
import time
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Importar templates disponíveis
from libs.VideosTemplates.TemplateDefault import TemplateDefault

# Dicionário de templates disponíveis
AVAILABLE_TEMPLATES = {
    "default": TemplateDefault,
    # Adicione outros templates aqui conforme necessário
    # "advanced": TemplateAdvanced,
    # "minimal": TemplateMinimal,
}


def get_template_class(template_name):
    """
    Retorna a classe do template baseado no nome.
    
    Args:
        template_name: Nome do template (ex: "default", "advanced")
    
    Returns:
        Classe do template ou None se não encontrado
    """
    return AVAILABLE_TEMPLATES.get(template_name)


def process_video(video_config, index, total):
    """
    Processa um único vídeo usando o template especificado.
    
    Args:
        video_config: Dicionário com as configurações do vídeo
        index: Índice do vídeo atual
        total: Total de vídeos a processar
    
    Returns:
        True se sucesso, False se erro
    """
    print(f"\n{'='*60}")
    print(f"🎬 VÍDEO {index}/{total}")
    print(f"{'='*60}")
    
    # Obter template
    template_name = video_config.get("template", False)
    
    if not template_name:
        print("❌ Erro: Template não especificado. Pulando vídeo.")
        return False
    
    # Buscar classe do template
    template_class = get_template_class(template_name)
    
    if not template_class:
        print(f"❌ Erro: Template '{template_name}' não reconhecido.")
        print(f"📋 Templates disponíveis: {', '.join(AVAILABLE_TEMPLATES.keys())}")
        return False
    
    # Remover o campo 'template' do config para evitar conflitos
    video_config_clean = {k: v for k, v in video_config.items() if k != "template"}
    
    # Criar instância do template
    template = template_class(video_config_clean)
    
    # Validar configurações
    print(f"🔍 Validando configurações do template '{template_name}'...")
    errors = template.validate_configs()
    
    if errors:
        print(f"\n❌ Erro: Configurações inválidas para o template '{template_name}'.")
        print(f"\n{'='*60}")
        print("📋 Erros encontrados:")
        for error in errors:
            print(f"  ❌ {error}")
        print(f"{'='*60}")
        return False
    
    print("✅ Configurações validadas com sucesso!")
    
    # Processar vídeo
    return template.process()


def main():
    """Função principal que processa todos os vídeos do JSON."""
    print("\n" + "="*60)
    print("🎬 GERADOR DE VÍDEOS AUTOMATIZADO")
    print("="*60)
    
    start_time = time.time()
    
    # Determinar arquivo JSON
    if os.getenv("DEBUG") == "1":
        json_file = os.getenv("DEFAULT_JSON_DEBUG", "json_teste.json")
        print(f"🔧 Modo DEBUG ativado")
    else:
        json_file = input("\n📂 Informe o caminho do arquivo JSON de configuração: ").strip()
        if not json_file:
            json_file = "json_teste.json"  # Padrão

    # print listar pastas e arquivos no diretório atual
    print(f"\n📁 Diretório atual: {os.getcwd()}")
    print(f"📂 Conteúdo do diretório atual: {os.listdir(os.getcwd())}")

    print(f"\n📁 Arquivo JSON selecionado: {json_file}")
    
    # Verificar se arquivo existe
    if not os.path.exists(json_file):
        print(f"\n❌ Erro: Arquivo '{json_file}' não encontrado!")
        print("💡 Crie um arquivo JSON com suas configurações.")
        print("\n📋 Exemplo de estrutura:")
        print("""
[
  {
    "template": "default",
    "slug": "meu-video",
    "content": {
      "title": "Título do Vídeo",
      "description": "Descrição...",
      "hashtags": "#tag1 #tag2"
    },
    "background": {
      "videos_dir": "caminho/para/videos",
      "music_dir": false
    },
    "tts": {
      "narration_text": "Texto da narração...",
      "edge_tts": {
        "voice_id": "pt-BR-FranciscaNeural"
      }
    },
    "output_ratio": "9:16",
    "headline": false,
    "youtube": false
  }
]
        """)
        return
    
    # Carregar configurações
    print(f"\n📂 Carregando configurações de: {json_file}")
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            videos_config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"\n❌ Erro ao ler JSON: {e}")
        return
    except Exception as e:
        print(f"\n❌ Erro ao abrir arquivo: {e}")
        return
    
    # Validar estrutura do JSON
    if not isinstance(videos_config, list):
        print("\n❌ Erro: O JSON deve conter uma lista de vídeos!")
        return
    
    if len(videos_config) == 0:
        print("\n⚠️ Nenhum vídeo encontrado no arquivo JSON.")
        return
    
    print(f"✅ {len(videos_config)} vídeo(s) encontrado(s)")
    
    # Criar pasta de saída principal
    os.makedirs("output", exist_ok=True)
    
    # Ordenar vídeos por data de publicação (se houver)
    videos_with_schedule = [v for v in videos_config 
                           if v.get("youtube") and v["youtube"].get("publish_at")]
    
    if videos_with_schedule:
        print("\n📅 Ordenando vídeos por data de agendamento...")
        videos_config.sort(
            key=lambda v: (
                not (v.get("youtube") and v["youtube"].get("publish_at")),
                v.get("youtube", {}).get("publish_at", "")
            )
        )
    
    # Processar cada vídeo
    success_count = 0
    error_count = 0
    
    for index, video_config in enumerate(videos_config, 1):
        try:
            if process_video(video_config, index, len(videos_config)):
                success_count += 1
                print(f"\n✅ Vídeo {index} processado com sucesso!")
            else:
                error_count += 1
                print(f"\n❌ Erro ao processar vídeo {index}")
        except KeyboardInterrupt:
            print("\n\n⚠️ Processamento interrompido pelo usuário.")
            break
        except Exception as e:
            print(f"\n❌ ERRO INESPERADO ao processar vídeo {index}: {e}")
            import traceback
            traceback.print_exc()
            error_count += 1
            continue
    
    # Resumo final
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    print("\n" + "="*60)
    print("🏁 PROCESSAMENTO CONCLUÍDO")
    print("="*60)
    print(f"✅ Vídeos gerados com sucesso: {success_count}")
    print(f"❌ Vídeos com erro: {error_count}")
    print(f"⏱️ Tempo total: {elapsed_time:.2f}s ({elapsed_time/60:.1f} minutos)")
    
    if success_count > 0:
        print(f"📁 Vídeos salvos em: ./output/")
    
    print("="*60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Programa encerrado pelo usuário.")
    except Exception as e:
        print(f"\n❌ ERRO FATAL: {e}")
        import traceback
        traceback.print_exc()