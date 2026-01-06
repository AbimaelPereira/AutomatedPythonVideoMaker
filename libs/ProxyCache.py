import os
import json
import hashlib
import subprocess
import tempfile
import shutil
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class ProxyCache:
    """
    Manages proxy video generation and caching for reducing memory usage.
    
    Proxies are low-resolution versions of source videos that are used during
    video generation to reduce memory consumption. The original high-resolution
    videos are used only for final export when proxies are disabled.
    """
    
    def __init__(self, cache_dir="./cache/proxies", resolution="1280x720", 
                 bitrate=None, regen_on_source_change=True, crf=28, timeout=300):
        """
        Initialize ProxyCache.
        
        Args:
            cache_dir: Directory to store proxy files
            resolution: Target resolution for proxies (e.g., "1280x720")
            bitrate: Optional bitrate for proxy encoding (e.g., "2M")
            regen_on_source_change: If True, regenerate proxy when source mtime changes
            crf: Constant Rate Factor for quality (0-51, higher = lower quality, default: 28)
            timeout: Timeout in seconds for ffmpeg operations (default: 300)
        """
        self.cache_dir = Path(cache_dir)
        self.resolution = resolution
        self.bitrate = bitrate
        self.regen_on_source_change = regen_on_source_change
        self.crf = crf
        self.timeout = timeout
        
        # Create cache directory if it doesn't exist
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"ProxyCache initialized with cache_dir={cache_dir}, resolution={resolution}")
    
    def _compute_proxy_filename(self, src_path):
        """
        Compute a unique proxy filename based on the source path.
        
        Args:
            src_path: Path to the source video file
            
        Returns:
            Tuple of (proxy_path, metadata_path)
        """
        # Use hash of absolute path to create unique filename
        abs_path = os.path.abspath(src_path)
        path_hash = hashlib.md5(abs_path.encode()).hexdigest()
        
        # Include resolution in filename for easy identification
        base_name = f"proxy_{path_hash}_{self.resolution.replace('x', '_')}"
        proxy_path = self.cache_dir / f"{base_name}.mp4"
        metadata_path = self.cache_dir / f"{base_name}.json"
        
        return proxy_path, metadata_path
    
    def _get_metadata(self, metadata_path, src_path):
        """
        Read metadata file for a proxy.
        
        Args:
            metadata_path: Path to the metadata file
            src_path: Path to the source video file
            
        Returns:
            Dictionary with metadata or None if invalid/missing
        """
        if not metadata_path.exists():
            return None
        
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            # Validate metadata structure
            required_keys = ['source_path', 'source_mtime', 'generation_timestamp', 'resolution']
            if not all(key in metadata for key in required_keys):
                logger.warning(f"Invalid metadata file: {metadata_path}")
                return None
            
            return metadata
            
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read metadata file {metadata_path}: {e}")
            return None
    
    def _write_metadata(self, metadata_path, src_path):
        """
        Write metadata file for a proxy.
        
        Args:
            metadata_path: Path to the metadata file
            src_path: Path to the source video file
        """
        src_stat = os.stat(src_path)
        metadata = {
            'source_path': os.path.abspath(src_path),
            'source_mtime': src_stat.st_mtime,
            'generation_timestamp': time.time(),
            'resolution': self.resolution,
        }
        
        # Write atomically using temp file + rename
        with tempfile.NamedTemporaryFile(
            mode='w', 
            dir=self.cache_dir, 
            delete=False,
            suffix='.json.tmp'
        ) as tmp_file:
            json.dump(metadata, tmp_file, indent=2)
            tmp_path = tmp_file.name
        
        # Atomic rename
        os.replace(tmp_path, metadata_path)
        logger.debug(f"Wrote metadata to {metadata_path}")
    
    def _is_proxy_valid(self, proxy_path, metadata_path, src_path):
        """
        Check if a proxy is valid and up-to-date.
        
        Args:
            proxy_path: Path to the proxy file
            metadata_path: Path to the metadata file
            src_path: Path to the source video file
            
        Returns:
            True if proxy is valid, False otherwise
        """
        # Check if files exist
        if not proxy_path.exists() or not metadata_path.exists():
            return False
        
        # Read metadata
        metadata = self._get_metadata(metadata_path, src_path)
        if not metadata:
            return False
        
        # Check if resolution matches
        if metadata.get('resolution') != self.resolution:
            logger.info(f"Proxy resolution mismatch for {src_path}: "
                       f"expected {self.resolution}, got {metadata.get('resolution')}")
            return False
        
        # Check if source file has changed
        if self.regen_on_source_change:
            try:
                src_stat = os.stat(src_path)
                if src_stat.st_mtime != metadata.get('source_mtime'):
                    logger.info(f"Source file modified, proxy needs regeneration: {src_path}")
                    return False
            except OSError as e:
                logger.warning(f"Failed to stat source file {src_path}: {e}")
                return False
        
        return True
    
    def _generate_proxy(self, src_path, proxy_path):
        """
        Generate a proxy video using ffmpeg.
        
        Args:
            src_path: Path to the source video file
            proxy_path: Path where the proxy should be written
            
        Raises:
            RuntimeError: If ffmpeg fails to generate the proxy
        """
        logger.info(f"Generating proxy for {os.path.basename(src_path)} "
                   f"at resolution {self.resolution}")
        
        # Parse resolution
        try:
            width, height = map(int, self.resolution.split('x'))
        except ValueError:
            raise ValueError(f"Invalid resolution format: {self.resolution}")
        
        # Build ffmpeg command
        # Use a temp file for atomic write - create with .mp4 extension for ffmpeg
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self.cache_dir,
            suffix='.mp4',
            prefix='tmp_proxy_'
        )
        os.close(tmp_fd)  # Close the file descriptor, ffmpeg will write to it
        
        try:
            cmd = [
                'ffmpeg',
                '-i', src_path,
                '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', str(self.crf),
                '-an',  # No audio for proxies
                '-y',  # Overwrite output file
            ]
            
            # Add bitrate if specified
            if self.bitrate:
                cmd.extend(['-b:v', self.bitrate])
            
            cmd.append(tmp_path)
            
            # Run ffmpeg
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.decode('utf-8', errors='ignore')
                raise RuntimeError(
                    f"ffmpeg failed with return code {result.returncode}: {error_msg}"
                )
            
            # Atomic rename from temp to final path
            os.replace(tmp_path, proxy_path)
            logger.info(f"Proxy created successfully: {proxy_path}")
            
        except subprocess.TimeoutExpired:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise RuntimeError(f"ffmpeg timeout while generating proxy for {src_path}")
        
        except Exception as e:
            # Clean up temp file on any error
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise RuntimeError(f"Failed to generate proxy for {src_path}: {e}")
    
    def get_or_create(self, src_path):
        """
        Get the proxy path for a source video, creating it if necessary.
        
        This is the main entry point for the ProxyCache. It will:
        1. Check if a valid proxy exists
        2. If not, generate a new proxy
        3. Return the path to the proxy
        
        Args:
            src_path: Path to the source video file
            
        Returns:
            Path to the proxy video (as string)
            
        Raises:
            RuntimeError: If proxy generation fails
            FileNotFoundError: If source file doesn't exist
        """
        # Validate source file exists
        if not os.path.exists(src_path):
            raise FileNotFoundError(f"Source video not found: {src_path}")
        
        proxy_path, metadata_path = self._compute_proxy_filename(src_path)
        
        # Check if valid proxy exists
        if self._is_proxy_valid(proxy_path, metadata_path, src_path):
            logger.debug(f"📦 Using cached proxy for {os.path.basename(src_path)}")
            return str(proxy_path)
        
        # Generate new proxy
        try:
            self._generate_proxy(src_path, proxy_path)
            self._write_metadata(metadata_path, src_path)
            return str(proxy_path)
            
        except Exception as e:
            logger.error(f"Failed to generate proxy for {src_path}: {e}")
            # Clean up partial files
            if proxy_path.exists():
                proxy_path.unlink()
            if metadata_path.exists():
                metadata_path.unlink()
            raise
