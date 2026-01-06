import os
import json
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ProxyCache:
    """
    Manages proxy video generation and caching for background clips.
    
    Proxies are lower-resolution versions of source videos that improve
    performance during editing. They are generated atomically and cached
    with metadata to track source file changes.
    """
    
    DEFAULT_CACHE_DIR = "./cache/proxies"
    DEFAULT_PROXY_WIDTH = 1280
    DEFAULT_PROXY_HEIGHT = 720
    
    def __init__(self, cache_dir=None, proxy_width=None, proxy_height=None):
        """
        Initialize the ProxyCache.
        
        Args:
            cache_dir: Directory to store proxy files. Defaults to ./cache/proxies
            proxy_width: Width of proxy videos. Defaults to 1280
            proxy_height: Height of proxy videos. Defaults to 720
        """
        self.cache_dir = cache_dir or self.DEFAULT_CACHE_DIR
        self.proxy_width = proxy_width or self.DEFAULT_PROXY_WIDTH
        self.proxy_height = proxy_height or self.DEFAULT_PROXY_HEIGHT
        
        # Ensure cache directory exists
        os.makedirs(self.cache_dir, exist_ok=True)
        logger.info(f"ProxyCache initialized with cache_dir={self.cache_dir}, resolution={self.proxy_width}x{self.proxy_height}")
    
    def get_or_create(self, src_path):
        """
        Get the proxy path for a source video, creating it if necessary.
        
        Args:
            src_path: Path to the source video file
            
        Returns:
            Path to the proxy video file. Returns src_path if proxy generation fails.
        """
        if not os.path.exists(src_path):
            logger.error(f"Source video not found: {src_path}")
            return src_path
        
        # Generate proxy filename based on source path hash
        src_path_abs = os.path.abspath(src_path)
        proxy_name = self._generate_proxy_name(src_path_abs)
        proxy_path = os.path.join(self.cache_dir, proxy_name)
        metadata_path = proxy_path + ".meta.json"
        
        # Check if proxy is up to date
        if self.is_proxy_up_to_date(src_path_abs, proxy_path, metadata_path):
            logger.debug(f"Using cached proxy: {proxy_path}")
            return proxy_path
        
        # Generate new proxy
        logger.info(f"Generating proxy for: {src_path_abs}")
        success = self.generate_proxy(src_path_abs, proxy_path, metadata_path)
        
        if success:
            logger.info(f"Proxy created successfully: {proxy_path}")
            return proxy_path
        else:
            logger.warning(f"Proxy generation failed, using original: {src_path}")
            return src_path
    
    def is_proxy_up_to_date(self, src_path, proxy_path, metadata_path):
        """
        Check if a proxy is up to date with its source file.
        
        Args:
            src_path: Path to the source video file
            proxy_path: Path to the proxy video file
            metadata_path: Path to the proxy metadata file
            
        Returns:
            True if proxy exists and is up to date, False otherwise
        """
        # Check if proxy and metadata exist
        if not os.path.exists(proxy_path) or not os.path.exists(metadata_path):
            return False
        
        try:
            # Read metadata
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            # Get source file mtime
            src_mtime = os.path.getmtime(src_path)
            
            # Compare mtimes
            if metadata.get('src_mtime') == src_mtime:
                return True
            else:
                logger.debug(f"Source file modified, proxy needs regeneration: {src_path}")
                return False
                
        except Exception as e:
            logger.error(f"Error reading proxy metadata: {e}")
            return False
    
    def generate_proxy(self, src_path, proxy_path, metadata_path):
        """
        Generate a proxy video using ffmpeg with atomic write (tmp -> rename).
        
        Args:
            src_path: Path to the source video file
            proxy_path: Path to the destination proxy file
            metadata_path: Path to the metadata file
            
        Returns:
            True if successful, False otherwise
        """
        tmp_proxy_path = proxy_path + ".tmp"
        tmp_metadata_path = metadata_path + ".tmp"
        
        try:
            # Build ffmpeg command for proxy generation
            # -i: input file
            # -vf scale: resize video to proxy resolution, maintaining aspect ratio
            # -c:v libx264: use H.264 codec
            # -preset fast: encoding speed/quality tradeoff
            # -crf 23: quality (lower = better quality, 23 is good default)
            # -an: no audio (we don't need audio for background clips)
            # -y: overwrite output file
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', src_path,
                '-vf', f'scale={self.proxy_width}:{self.proxy_height}:force_original_aspect_ratio=decrease,pad={self.proxy_width}:{self.proxy_height}:(ow-iw)/2:(oh-ih)/2',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-an',  # no audio
                '-y',
                tmp_proxy_path
            ]
            
            logger.debug(f"Running ffmpeg command: {' '.join(ffmpeg_cmd)}")
            
            # Run ffmpeg
            result = subprocess.run(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
            
            # Create metadata
            src_mtime = os.path.getmtime(src_path)
            metadata = {
                'src_path': src_path,
                'src_mtime': src_mtime,
                'proxy_width': self.proxy_width,
                'proxy_height': self.proxy_height,
                'proxy_path': proxy_path
            }
            
            # Write metadata to tmp file
            with open(tmp_metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            # Atomic rename: tmp -> final
            os.rename(tmp_proxy_path, proxy_path)
            os.rename(tmp_metadata_path, metadata_path)
            
            logger.info(f"Proxy generated successfully: {proxy_path}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg error generating proxy: {e.stderr.decode() if e.stderr else str(e)}")
            # Clean up tmp files if they exist
            if os.path.exists(tmp_proxy_path):
                os.remove(tmp_proxy_path)
            if os.path.exists(tmp_metadata_path):
                os.remove(tmp_metadata_path)
            return False
            
        except Exception as e:
            logger.error(f"Error generating proxy: {e}")
            # Clean up tmp files if they exist
            if os.path.exists(tmp_proxy_path):
                os.remove(tmp_proxy_path)
            if os.path.exists(tmp_metadata_path):
                os.remove(tmp_metadata_path)
            return False
    
    def _generate_proxy_name(self, src_path):
        """
        Generate a unique proxy filename based on the source path.
        
        Args:
            src_path: Absolute path to the source video file
            
        Returns:
            Proxy filename (without directory path)
        """
        import hashlib
        
        # Create hash of source path for unique filename
        path_hash = hashlib.md5(src_path.encode()).hexdigest()[:16]
        
        # Get original file extension
        _, ext = os.path.splitext(src_path)
        if not ext:
            ext = '.mp4'
        
        return f"proxy_{path_hash}{ext}"
