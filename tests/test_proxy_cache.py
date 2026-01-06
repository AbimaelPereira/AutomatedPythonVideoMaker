import os
import sys
import time
import tempfile
import shutil
import subprocess
import unittest

# Add parent directory to path to import libs
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.ProxyCache import ProxyCache


class TestProxyCache(unittest.TestCase):
    """Test suite for ProxyCache functionality"""
    
    def setUp(self):
        """Set up test environment before each test"""
        # Create temporary directories for testing
        self.test_dir = tempfile.mkdtemp()
        self.cache_dir = os.path.join(self.test_dir, "cache")
        self.video_dir = os.path.join(self.test_dir, "videos")
        os.makedirs(self.video_dir, exist_ok=True)
        
        # Create a simple test video using ffmpeg
        self.test_video_path = os.path.join(self.video_dir, "test_video.mp4")
        self._create_test_video(self.test_video_path)
        
        # Initialize ProxyCache with test configuration
        self.proxy_cache = ProxyCache({
            "proxy_enabled": True,
            "proxy_resolution": "640x360",
            "proxy_cache_dir": self.cache_dir,
            "proxy_regen_on_source_change": True,
        })
    
    def tearDown(self):
        """Clean up after each test"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def _create_test_video(self, output_path, duration=2, resolution="1920x1080"):
        """
        Create a simple test video using ffmpeg.
        
        Args:
            output_path: Path where the video will be created
            duration: Duration of the video in seconds
            resolution: Video resolution (WxH)
        """
        try:
            # Create a simple color video with ffmpeg
            cmd = [
                'ffmpeg',
                '-f', 'lavfi',
                '-i', f'color=c=blue:s={resolution}:d={duration}',
                '-pix_fmt', 'yuv420p',
                '-y',
                output_path
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=True)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            # If ffmpeg is not available or fails, skip the test
            self.skipTest(f"Cannot create test video: {e}")
    
    def test_proxy_generation(self):
        """Test that proxy is generated for a source video"""
        proxy_path = self.proxy_cache.generate_proxy(self.test_video_path)
        
        self.assertIsNotNone(proxy_path, "Proxy generation should return a path")
        self.assertTrue(os.path.exists(proxy_path), "Proxy file should exist")
        
        # Check that metadata file was created
        metadata_path = self.proxy_cache.get_metadata_path(proxy_path)
        self.assertTrue(os.path.exists(metadata_path), "Metadata file should exist")
    
    def test_proxy_usage(self):
        """Test that get_or_create_proxy returns proxy path"""
        # First call should generate proxy
        proxy_path = self.proxy_cache.get_or_create_proxy(self.test_video_path)
        
        self.assertTrue(os.path.exists(proxy_path), "Proxy should exist after get_or_create_proxy")
        
        # Second call should use existing proxy
        proxy_path_2 = self.proxy_cache.get_or_create_proxy(self.test_video_path)
        self.assertEqual(proxy_path, proxy_path_2, "Should return same proxy on second call")
    
    def test_proxy_invalidation_on_source_change(self):
        """Test that proxy is regenerated when source video is modified"""
        # Generate initial proxy
        proxy_path_1 = self.proxy_cache.get_or_create_proxy(self.test_video_path)
        initial_mtime = os.path.getmtime(proxy_path_1)
        
        # Wait a bit to ensure timestamp difference
        time.sleep(1.5)
        
        # Modify the source video (touch to update mtime)
        os.utime(self.test_video_path, None)
        
        # Request proxy again - should regenerate
        proxy_path_2 = self.proxy_cache.get_or_create_proxy(self.test_video_path)
        new_mtime = os.path.getmtime(proxy_path_2)
        
        self.assertEqual(proxy_path_1, proxy_path_2, "Proxy path should be the same")
        self.assertGreater(new_mtime, initial_mtime, "Proxy should be regenerated with newer mtime")
    
    def test_proxy_disabled(self):
        """Test that proxies are bypassed when disabled"""
        disabled_cache = ProxyCache({
            "proxy_enabled": False,
            "proxy_cache_dir": self.cache_dir,
        })
        
        result_path = disabled_cache.get_or_create_proxy(self.test_video_path)
        self.assertEqual(result_path, self.test_video_path, "Should return source path when proxies disabled")
    
    def test_cache_stats(self):
        """Test that cache statistics are correctly reported"""
        # Initially cache should be empty
        stats = self.proxy_cache.get_cache_stats()
        self.assertEqual(stats['total_files'], 0, "Cache should start empty")
        
        # Generate a proxy
        self.proxy_cache.get_or_create_proxy(self.test_video_path)
        
        # Check stats again
        stats = self.proxy_cache.get_cache_stats()
        self.assertEqual(stats['total_files'], 1, "Cache should have 1 file")
        self.assertGreater(stats['total_size_mb'], 0, "Cache size should be greater than 0")
    
    def test_nonexistent_source(self):
        """Test handling of non-existent source video"""
        fake_path = "/path/to/nonexistent/video.mp4"
        result = self.proxy_cache.generate_proxy(fake_path)
        self.assertIsNone(result, "Should return None for non-existent source")


if __name__ == '__main__':
    unittest.main()
