#!/usr/bin/env python3
"""
Integration test for proxy cache system.
This test verifies that proxies are created and used during video processing.
"""

import os
import sys
import tempfile
import shutil
import subprocess

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.BackgroundVideo import BackgroundVideo
from libs.ProxyCache import ProxyCache


# Test video directory (created in setup)
TEST_VIDEO_DIR = None


def setup_test_videos():
    """Create test videos in a temporary directory"""
    global TEST_VIDEO_DIR
    TEST_VIDEO_DIR = tempfile.mkdtemp()
    
    # Create two test videos
    for i, color in enumerate(['blue', 'red'], 1):
        video_path = os.path.join(TEST_VIDEO_DIR, f'sample{i}.mp4')
        try:
            cmd = [
                'ffmpeg', '-f', 'lavfi', '-i', f'color=c={color}:s=1920x1080:d=3',
                '-pix_fmt', 'yuv420p', '-y', video_path
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=True)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"❌ Failed to create test video: {e}")
            return False
    
    return True


def cleanup_test_videos():
    """Clean up test video directory"""
    global TEST_VIDEO_DIR
    if TEST_VIDEO_DIR and os.path.exists(TEST_VIDEO_DIR):
        shutil.rmtree(TEST_VIDEO_DIR)


def test_background_video_with_proxies():
    """Test that BackgroundVideo uses proxies correctly"""
    
    # Setup test environment
    test_cache_dir = tempfile.mkdtemp()
    
    print("\n🧪 Testing Proxy Integration with BackgroundVideo\n")
    print(f"Test video directory: {TEST_VIDEO_DIR}")
    print(f"Test cache directory: {test_cache_dir}\n")
    
    try:
        # Create BackgroundVideo instance with proxy enabled
        bg_video = BackgroundVideo(params={
            "background_videos_dir": TEST_VIDEO_DIR,
            "resolution_output": (1080, 1920),
            "max_clip_duration": 2,
            "proxy_enabled": True,
            "proxy_resolution": "640x360",
            "proxy_cache_dir": test_cache_dir,
        })
        
        print("✅ BackgroundVideo instance created with proxy enabled")
        
        # Get processed clips (should generate proxies)
        print("\n📹 Processing video clips (proxies will be generated)...\n")
        clips = bg_video.get_processed_clips()
        
        print(f"\n✅ Processed {len(clips)} clips")
        
        # Check that proxies were created
        proxy_cache = ProxyCache({
            "proxy_enabled": True,
            "proxy_cache_dir": test_cache_dir,
        })
        
        stats = proxy_cache.get_cache_stats()
        print(f"\n📊 Cache Statistics:")
        print(f"   Total files: {stats['total_files']}")
        print(f"   Total size: {stats['total_size_mb']:.2f} MB")
        
        if stats['total_files'] > 0:
            print("\n✅ SUCCESS: Proxies were created and used!")
        else:
            print("\n⚠️  WARNING: No proxies were created")
        
        # Clean up clips
        for clip in clips:
            try:
                clip.close()
            except Exception as e:
                # Specific exception handling for clip cleanup
                print(f"Note: Could not close clip: {e}")
        
        return stats['total_files'] > 0
        
    finally:
        # Clean up
        if os.path.exists(test_cache_dir):
            shutil.rmtree(test_cache_dir)


def test_proxy_disabled():
    """Test that proxies can be disabled"""
    
    test_cache_dir = tempfile.mkdtemp()
    
    print("\n🧪 Testing Proxy Disabled Mode\n")
    
    try:
        bg_video = BackgroundVideo(params={
            "background_videos_dir": TEST_VIDEO_DIR,
            "resolution_output": (1080, 1920),
            "max_clip_duration": 2,
            "proxy_enabled": False,  # Disabled
            "proxy_cache_dir": test_cache_dir,
        })
        
        print("✅ BackgroundVideo instance created with proxy DISABLED")
        
        # Get processed clips (should NOT generate proxies)
        print("\n📹 Processing video clips (no proxies)...\n")
        clips = bg_video.get_processed_clips()
        
        print(f"\n✅ Processed {len(clips)} clips")
        
        # Check that no proxies were created
        proxy_cache = ProxyCache({
            "proxy_enabled": False,
            "proxy_cache_dir": test_cache_dir,
        })
        
        stats = proxy_cache.get_cache_stats()
        
        if stats['total_files'] == 0:
            print("✅ SUCCESS: No proxies created when disabled!")
        else:
            print(f"⚠️  WARNING: {stats['total_files']} proxies were created despite being disabled")
        
        # Clean up clips
        for clip in clips:
            try:
                clip.close()
            except Exception as e:
                # Specific exception handling for clip cleanup
                print(f"Note: Could not close clip: {e}")
        
        return stats['total_files'] == 0
        
    finally:
        # Clean up
        if os.path.exists(test_cache_dir):
            shutil.rmtree(test_cache_dir)


if __name__ == "__main__":
    print("=" * 60)
    print("PROXY CACHE INTEGRATION TEST")
    print("=" * 60)
    
    success = True
    
    # Setup test videos
    print("\n📹 Creating test videos...")
    if not setup_test_videos():
        print("❌ Failed to create test videos. Skipping tests.")
        sys.exit(1)
    
    print(f"✅ Test videos created in {TEST_VIDEO_DIR}\n")
    
    # Run tests
    try:
        test1_result = test_background_video_with_proxies()
        test2_result = test_proxy_disabled()
        
        success = test1_result and test2_result
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        success = False
    
    finally:
        # Clean up test videos
        cleanup_test_videos()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 60)
    
    sys.exit(0 if success else 1)
