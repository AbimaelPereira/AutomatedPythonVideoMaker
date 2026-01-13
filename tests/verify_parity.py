#!/usr/bin/env python3
"""
Script de verificação de paridade para validar que o vídeo gerado
mantém as mesmas características após refatoração.

Valida:
- Duração total (±0.01s tolerância)
- Resolução (largura x altura)
- FPS (frames per second)
- Codecs de vídeo e áudio
- Presença de áudio
- Tamanho do arquivo (±3% tolerância)
"""

import os
import sys
import json
import subprocess
import argparse
from pathlib import Path


class ParityChecker:
    """Verifica paridade entre vídeos usando ffprobe."""
    
    def __init__(self, tolerance_duration=0.01, tolerance_size_percent=3.0):
        self.tolerance_duration = tolerance_duration
        self.tolerance_size_percent = tolerance_size_percent
    
    def get_video_metadata(self, video_path):
        """Extrai metadata do vídeo usando ffprobe."""
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Vídeo não encontrado: {video_path}")
        
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Erro ao executar ffprobe: {e}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Erro ao parsear JSON do ffprobe: {e}")
    
    def extract_key_properties(self, metadata):
        """Extrai propriedades chave do metadata."""
        props = {
            "duration": None,
            "width": None,
            "height": None,
            "fps": None,
            "video_codec": None,
            "audio_codec": None,
            "has_audio": False,
            "file_size": None
        }
        
        # Formato e tamanho
        if "format" in metadata:
            props["duration"] = float(metadata["format"].get("duration", 0))
            props["file_size"] = int(metadata["format"].get("size", 0))
        
        # Streams
        for stream in metadata.get("streams", []):
            if stream.get("codec_type") == "video":
                props["width"] = stream.get("width")
                props["height"] = stream.get("height")
                props["video_codec"] = stream.get("codec_name")
                
                # FPS pode estar em vários formatos
                fps_str = stream.get("r_frame_rate", "0/1")
                if "/" in fps_str:
                    num, den = map(int, fps_str.split("/"))
                    props["fps"] = num / den if den != 0 else 0
                else:
                    props["fps"] = float(fps_str)
            
            elif stream.get("codec_type") == "audio":
                props["has_audio"] = True
                props["audio_codec"] = stream.get("codec_name")
        
        return props
    
    def compare_videos(self, baseline_path, test_path):
        """Compara dois vídeos e retorna diferenças."""
        print(f"📊 Comparando vídeos:")
        print(f"   Baseline: {baseline_path}")
        print(f"   Test:     {test_path}")
        print()
        
        baseline_meta = self.get_video_metadata(baseline_path)
        test_meta = self.get_video_metadata(test_path)
        
        baseline_props = self.extract_key_properties(baseline_meta)
        test_props = self.extract_key_properties(test_meta)
        
        differences = []
        
        # Comparar duração
        if baseline_props["duration"] and test_props["duration"]:
            diff = abs(baseline_props["duration"] - test_props["duration"])
            if diff > self.tolerance_duration:
                differences.append({
                    "property": "duration",
                    "baseline": baseline_props["duration"],
                    "test": test_props["test"],
                    "diff": diff,
                    "status": "FAIL"
                })
            else:
                print(f"✅ Duração: {baseline_props['duration']:.2f}s vs {test_props['duration']:.2f}s (diff: {diff:.3f}s)")
        
        # Comparar resolução
        if baseline_props["width"] == test_props["width"] and baseline_props["height"] == test_props["height"]:
            print(f"✅ Resolução: {baseline_props['width']}x{baseline_props['height']}")
        else:
            differences.append({
                "property": "resolution",
                "baseline": f"{baseline_props['width']}x{baseline_props['height']}",
                "test": f"{test_props['width']}x{test_props['height']}",
                "status": "FAIL"
            })
        
        # Comparar FPS
        if baseline_props["fps"] and test_props["fps"]:
            if abs(baseline_props["fps"] - test_props["fps"]) < 0.1:
                print(f"✅ FPS: {baseline_props['fps']:.2f}")
            else:
                differences.append({
                    "property": "fps",
                    "baseline": baseline_props["fps"],
                    "test": test_props["fps"],
                    "status": "FAIL"
                })
        
        # Comparar codecs
        if baseline_props["video_codec"] == test_props["video_codec"]:
            print(f"✅ Codec de vídeo: {baseline_props['video_codec']}")
        else:
            differences.append({
                "property": "video_codec",
                "baseline": baseline_props["video_codec"],
                "test": test_props["video_codec"],
                "status": "FAIL"
            })
        
        if baseline_props["audio_codec"] == test_props["audio_codec"]:
            print(f"✅ Codec de áudio: {baseline_props['audio_codec']}")
        else:
            differences.append({
                "property": "audio_codec",
                "baseline": baseline_props["audio_codec"],
                "test": test_props["audio_codec"],
                "status": "FAIL"
            })
        
        # Verificar presença de áudio
        if baseline_props["has_audio"] == test_props["has_audio"]:
            print(f"✅ Áudio presente: {baseline_props['has_audio']}")
        else:
            differences.append({
                "property": "has_audio",
                "baseline": baseline_props["has_audio"],
                "test": test_props["has_audio"],
                "status": "FAIL"
            })
        
        # Comparar tamanho do arquivo
        if baseline_props["file_size"] and test_props["file_size"]:
            size_diff_percent = abs(baseline_props["file_size"] - test_props["file_size"]) / baseline_props["file_size"] * 100
            if size_diff_percent <= self.tolerance_size_percent:
                print(f"✅ Tamanho do arquivo: {baseline_props['file_size']} vs {test_props['file_size']} bytes (diff: {size_diff_percent:.2f}%)")
            else:
                differences.append({
                    "property": "file_size",
                    "baseline": baseline_props["file_size"],
                    "test": test_props["file_size"],
                    "diff_percent": size_diff_percent,
                    "status": "WARN"
                })
        
        return differences, baseline_props, test_props
    
    def save_baseline(self, video_path, baseline_file):
        """Salva metadata do baseline para comparação futura."""
        metadata = self.get_video_metadata(video_path)
        props = self.extract_key_properties(metadata)
        
        with open(baseline_file, "w", encoding="utf-8") as f:
            json.dump(props, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Baseline salvo em: {baseline_file}")
        return props
    
    def load_baseline(self, baseline_file):
        """Carrega metadata do baseline."""
        if not os.path.exists(baseline_file):
            raise FileNotFoundError(f"Arquivo baseline não encontrado: {baseline_file}")
        
        with open(baseline_file, "r", encoding="utf-8") as f:
            return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Verifica paridade de vídeos")
    parser.add_argument("--mode", choices=["save", "compare"], required=True,
                      help="save: salva baseline, compare: compara com baseline")
    parser.add_argument("--baseline", required=True,
                      help="Caminho para o vídeo baseline ou arquivo JSON de metadata")
    parser.add_argument("--test", 
                      help="Caminho para o vídeo de teste (necessário para modo compare)")
    parser.add_argument("--tolerance-duration", type=float, default=0.01,
                      help="Tolerância de duração em segundos (padrão: 0.01)")
    parser.add_argument("--tolerance-size", type=float, default=3.0,
                      help="Tolerância de tamanho em porcentagem (padrão: 3.0)")
    
    args = parser.parse_args()
    
    checker = ParityChecker(
        tolerance_duration=args.tolerance_duration,
        tolerance_size_percent=args.tolerance_size
    )
    
    if args.mode == "save":
        # Salvar baseline
        if not args.baseline.endswith(".mp4"):
            print("❌ Para modo 'save', --baseline deve ser um arquivo .mp4")
            sys.exit(1)
        
        baseline_json = args.baseline.replace(".mp4", "_metadata.json")
        props = checker.save_baseline(args.baseline, baseline_json)
        
        print("\n📋 Propriedades do baseline:")
        for key, value in props.items():
            print(f"   {key}: {value}")
        
        print(f"\n✅ Baseline salvo com sucesso!")
    
    elif args.mode == "compare":
        # Comparar com baseline
        if not args.test:
            print("❌ Para modo 'compare', --test é obrigatório")
            sys.exit(1)
        
        # Baseline pode ser .mp4 ou .json
        if args.baseline.endswith(".json"):
            baseline_props = checker.load_baseline(args.baseline)
            test_meta = checker.get_video_metadata(args.test)
            test_props = checker.extract_key_properties(test_meta)
            
            # Comparação manual
            print(f"📊 Comparando com baseline: {args.baseline}")
            print(f"   Test: {args.test}")
            print()
            
            differences = []
            
            # Implementar comparações...
            for key in baseline_props:
                if baseline_props[key] != test_props.get(key):
                    differences.append({
                        "property": key,
                        "baseline": baseline_props[key],
                        "test": test_props.get(key),
                        "status": "FAIL"
                    })
                else:
                    print(f"✅ {key}: {baseline_props[key]}")
        
        else:
            # Comparar dois vídeos
            differences, baseline_props, test_props = checker.compare_videos(args.baseline, args.test)
        
        # Resultado
        print()
        if differences:
            print("❌ FALHA: Encontradas diferenças:")
            for diff in differences:
                print(f"   - {diff['property']}: baseline={diff.get('baseline')} test={diff.get('test')}")
            sys.exit(1)
        else:
            print("✅ SUCESSO: Paridade verificada!")
            sys.exit(0)


if __name__ == "__main__":
    main()
