#!/usr/bin/env python3
"""
Simple test script to verify ProxyCache functionality.
"""
import os
import sys
import logging

# Add libs to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'libs'))

from ProxyCache import ProxyCache

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_proxy_cache():
    """Test basic proxy cache functionality."""
    print("\n" + "="*60)
    print("Testing ProxyCache Module")
    print("="*60 + "\n")
    
    # Test video path
    test_video = "./assets/overlays/1.mp4"
    
    if not os.path.exists(test_video):
        print(f"❌ Test video not found: {test_video}")
        return False
    
    print(f"✅ Test video found: {test_video}")
    
    # Initialize ProxyCache
    cache = ProxyCache(
        cache_dir="./cache/proxies",
        resolution="640x360",  # Small resolution for quick testing
        regen_on_source_change=True
    )
    
    print("\n📦 Testing proxy generation (first call)...")
    try:
        proxy_path = cache.get_or_create(test_video)
        print(f"✅ Proxy generated successfully: {proxy_path}")
        
        if not os.path.exists(proxy_path):
            print(f"❌ Proxy file doesn't exist: {proxy_path}")
            return False
            
        proxy_size = os.path.getsize(proxy_path)
        print(f"   Proxy size: {proxy_size / 1024:.2f} KB")
        
    except Exception as e:
        print(f"❌ Failed to generate proxy: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n📦 Testing proxy reuse (second call)...")
    try:
        proxy_path2 = cache.get_or_create(test_video)
        print(f"✅ Proxy retrieved from cache: {proxy_path2}")
        
        if proxy_path != proxy_path2:
            print(f"❌ Proxy paths don't match!")
            return False
            
    except Exception as e:
        print(f"❌ Failed to retrieve cached proxy: {e}")
        return False
    
    print("\n" + "="*60)
    print("✅ All ProxyCache tests passed!")
    print("="*60 + "\n")
    return True

if __name__ == "__main__":
    success = test_proxy_cache()
    sys.exit(0 if success else 1)
