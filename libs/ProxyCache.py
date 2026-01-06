import os
import json
import hashlib
import time
import subprocess
from pathlib import Path


class ProxyCache:
    """
    Manages low-resolution proxy copies of video files to reduce memory usage.
    Proxies are cached on disk and regenerated when source files change.
    """
    
    def __init__(self, config=None):
        """
        Initialize the ProxyCache with configuration.
        
        Args:
            config: Configuration object or dict with proxy settings
        """
        defaults = {
            "proxy_enabled": True,
            "proxy_resolution": "1280x720",
            "proxy_bitrate": None,  # Let ffmpeg decide if not specified
            "proxy_cache_dir": "./cache/proxies",
            "proxy_regen_on_source_change": True,
        }
        
        if config:
            if hasattr(config, 'get'):
                # Config object with get method
                for key in defaults:
                    defaults[key] = config.get(key, defaults[key])
            else:
                # Plain dict
                defaults.update(config)
        
        for k, v in defaults.items():
            setattr(self, k, v)
        
        # Ensure cache directory exists
        if self.proxy_enabled:
            os.makedirs(self.proxy_cache_dir, exist_ok=True)
    
    def get_proxy_path(self, source_path):
        """
        Generate the cache path for a proxy file based on source path.
        
        Args:
            source_path: Path to the original video file
            
        Returns:
            Path to the proxy file in cache
        """
        # Create a unique filename based on the source path
        source_hash = hashlib.md5(source_path.encode()).hexdigest()[:16]
        source_name = Path(source_path).stem
        proxy_filename = f"{source_name}_{source_hash}_proxy.mp4"
        return os.path.join(self.proxy_cache_dir, proxy_filename)
    
    def get_metadata_path(self, proxy_path):
        """
        Get the path to the metadata file for a proxy.
        
        Args:
            proxy_path: Path to the proxy file
            
        Returns:
            Path to the metadata JSON file
        """
        return proxy_path + ".meta.json"
    
    def is_proxy_valid(self, source_path, proxy_path):
        """
        Check if a proxy file is valid (exists and up-to-date).
        
        Args:
            source_path: Path to the original video file
            proxy_path: Path to the proxy file
            
        Returns:
            True if proxy is valid, False otherwise
        """
        if not os.path.exists(proxy_path):
            return False
        
        if not self.proxy_regen_on_source_change:
            # If regeneration on change is disabled, existing proxy is valid
            return True
        
        # Check metadata
        metadata_path = self.get_metadata_path(proxy_path)
        if not os.path.exists(metadata_path):
            return False
        
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            # Compare source file modification time
            source_mtime = os.path.getmtime(source_path)
            cached_mtime = metadata.get('source_mtime', 0)
            
            return abs(source_mtime - cached_mtime) < 1.0  # Allow 1 second tolerance
        except Exception as e:
            print(f"[ProxyCache] Error reading metadata: {e}")
            return False
    
    def generate_proxy(self, source_path):
        """
        Generate a proxy video file from source.
        
        Args:
            source_path: Path to the original video file
            
        Returns:
            Path to the generated proxy file, or None on failure
        """
        if not os.path.exists(source_path):
            print(f"[ProxyCache] Source file not found: {source_path}")
            return None
        
        proxy_path = self.get_proxy_path(source_path)
        temp_path = proxy_path + ".tmp.mp4"
        
        print(f"[ProxyCache] Generating proxy for: {os.path.basename(source_path)}")
        start_time = time.time()
        
        try:
            # Build ffmpeg command
            cmd = [
                'ffmpeg',
                '-i', source_path,
                '-vf', f'scale={self.proxy_resolution}:force_original_aspect_ratio=decrease',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '28',  # Higher CRF = lower quality/size
            ]
            
            if self.proxy_bitrate:
                cmd.extend(['-b:v', self.proxy_bitrate])
            
            cmd.extend([
                '-an',  # No audio for background videos
                '-y',  # Overwrite output file
                temp_path
            ])
            
            # Run ffmpeg
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                print(f"[ProxyCache] ffmpeg error: {result.stderr.decode()[:200]}")
                return None
            
            # Atomic rename
            os.rename(temp_path, proxy_path)
            
            # Save metadata
            metadata = {
                'source_path': source_path,
                'source_mtime': os.path.getmtime(source_path),
                'proxy_resolution': self.proxy_resolution,
                'generated_at': time.time(),
            }
            
            metadata_path = self.get_metadata_path(proxy_path)
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            elapsed = time.time() - start_time
            print(f"[ProxyCache] ✅ Proxy generated in {elapsed:.2f}s: {os.path.basename(proxy_path)}")
            
            return proxy_path
            
        except subprocess.TimeoutExpired:
            print(f"[ProxyCache] Timeout generating proxy for {source_path}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return None
        except Exception as e:
            print(f"[ProxyCache] Error generating proxy: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return None
    
    def get_or_create_proxy(self, source_path):
        """
        Get the proxy for a source file, generating it if necessary.
        
        Args:
            source_path: Path to the original video file
            
        Returns:
            Path to the proxy file (or source if proxies disabled/failed)
        """
        if not self.proxy_enabled:
            return source_path
        
        proxy_path = self.get_proxy_path(source_path)
        
        # Check if valid proxy exists
        if self.is_proxy_valid(source_path, proxy_path):
            return proxy_path
        
        # Generate new proxy
        generated_path = self.generate_proxy(source_path)
        return generated_path if generated_path else source_path
    
    def get_cache_stats(self):
        """
        Get statistics about the proxy cache.
        
        Returns:
            Dict with cache statistics
        """
        if not os.path.exists(self.proxy_cache_dir):
            return {
                'enabled': self.proxy_enabled,
                'cache_dir': self.proxy_cache_dir,
                'total_files': 0,
                'total_size_mb': 0,
            }
        
        proxy_files = [f for f in os.listdir(self.proxy_cache_dir) if f.endswith('.mp4')]
        total_size = sum(
            os.path.getsize(os.path.join(self.proxy_cache_dir, f))
            for f in proxy_files
        )
        
        return {
            'enabled': self.proxy_enabled,
            'cache_dir': self.proxy_cache_dir,
            'total_files': len(proxy_files),
            'total_size_mb': total_size / (1024 * 1024),
        }
    
    def clear_cache(self):
        """
        Clear all proxy files from the cache.
        
        Returns:
            Number of files removed
        """
        if not os.path.exists(self.proxy_cache_dir):
            return 0
        
        count = 0
        for filename in os.listdir(self.proxy_cache_dir):
            filepath = os.path.join(self.proxy_cache_dir, filename)
            try:
                os.remove(filepath)
                count += 1
            except Exception as e:
                print(f"[ProxyCache] Error removing {filename}: {e}")
        
        return count
