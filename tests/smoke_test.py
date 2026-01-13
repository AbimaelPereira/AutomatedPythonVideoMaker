#!/usr/bin/env python3
"""
Basic smoke test to verify modular architecture can be imported and instantiated.
This doesn't generate a full video, just checks that the structure is correct.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_imports():
    """Test that all modules can be imported."""
    print("🔍 Testing imports...")
    
    try:
        from libs.services.SpeechService import SpeechService
        print("  ✅ SpeechService")
    except Exception as e:
        print(f"  ❌ SpeechService: {e}")
        return False
    
    try:
        from libs.services.AssetManager import AssetManager
        print("  ✅ AssetManager")
    except Exception as e:
        print(f"  ❌ AssetManager: {e}")
        return False
    
    try:
        from libs.services.SceneRenderer import SceneRenderer
        print("  ✅ SceneRenderer")
    except Exception as e:
        print(f"  ❌ SceneRenderer: {e}")
        return False
    
    try:
        from libs.services.AudioEngine import AudioEngine
        print("  ✅ AudioEngine")
    except Exception as e:
        print(f"  ❌ AudioEngine: {e}")
        return False
    
    try:
        from libs.pipeline.ExportPipeline import ExportPipeline
        print("  ✅ ExportPipeline")
    except Exception as e:
        print(f"  ❌ ExportPipeline: {e}")
        return False
    
    try:
        from libs.delivery.DeliveryService import DeliveryService
        print("  ✅ DeliveryService")
    except Exception as e:
        print(f"  ❌ DeliveryService: {e}")
        return False
    
    try:
        from libs.core.ConfigManager import ConfigManager
        print("  ✅ ConfigManager")
    except Exception as e:
        print(f"  ❌ ConfigManager: {e}")
        return False
    
    try:
        from libs.core.VideoOrchestrator import VideoOrchestrator
        print("  ✅ VideoOrchestrator")
    except Exception as e:
        print(f"  ❌ VideoOrchestrator: {e}")
        return False
    
    try:
        from libs.UnifiedVideoEngine import UnifiedVideoEngine
        print("  ✅ UnifiedVideoEngine")
    except Exception as e:
        print(f"  ❌ UnifiedVideoEngine: {e}")
        return False
    
    return True


def test_instantiation():
    """Test that classes can be instantiated with minimal config."""
    print("\n🔧 Testing instantiation...")
    
    # Minimal test config
    test_config = {
        "slug": "test",
        "output_ratio": "9:16",
        "scenes": []
    }
    
    try:
        from libs.UnifiedVideoEngine import UnifiedVideoEngine
        engine = UnifiedVideoEngine(test_config)
        print("  ✅ UnifiedVideoEngine instantiated")
    except Exception as e:
        print(f"  ❌ UnifiedVideoEngine instantiation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    try:
        from libs.core.VideoOrchestrator import VideoOrchestrator
        orchestrator = VideoOrchestrator(test_config)
        print("  ✅ VideoOrchestrator instantiated")
    except Exception as e:
        print(f"  ❌ VideoOrchestrator instantiation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


def test_api_compatibility():
    """Test that UnifiedVideoEngine maintains API compatibility."""
    print("\n🔌 Testing API compatibility...")
    
    from libs.UnifiedVideoEngine import UnifiedVideoEngine
    
    test_config = {
        "slug": "test",
        "output_ratio": "9:16",
        "scenes": []
    }
    
    engine = UnifiedVideoEngine(test_config)
    
    # Check attributes exist
    if not hasattr(engine, 'run'):
        print("  ❌ Missing 'run' method")
        return False
    print("  ✅ 'run' method exists")
    
    if not hasattr(engine, 'total_duration'):
        print("  ❌ Missing 'total_duration' attribute")
        return False
    print("  ✅ 'total_duration' attribute exists")
    
    if not hasattr(engine, 'VALID_AUDIO_EXTENSIONS'):
        print("  ❌ Missing 'VALID_AUDIO_EXTENSIONS' constant")
        return False
    print("  ✅ 'VALID_AUDIO_EXTENSIONS' constant exists")
    
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("🧪 Smoke Test - Modular Architecture")
    print("=" * 60)
    
    all_passed = True
    
    if not test_imports():
        all_passed = False
    
    if not test_instantiation():
        all_passed = False
    
    if not test_api_compatibility():
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All smoke tests passed!")
        print("=" * 60)
        return 0
    else:
        print("❌ Some tests failed!")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
