# Automated Python Video Maker

An automated video generation pipeline for creating videos from JSON configuration files.

## Features

- Text-to-speech narration generation
- Background video/image/color support
- Subtitle generation
- Visual elements (images, videos, GIFs)
- YouTube upload integration
- **Video Proxy Cache** for reduced memory usage during generation

## Video Proxy Cache

### What are Proxies?

Video proxies are low-resolution versions of your background video clips that are automatically generated and used during the video generation process. This significantly reduces memory consumption, especially when working with large or high-resolution background videos.

### Benefits

- **Reduced Memory Usage**: Proxies use much less RAM during video generation, allowing you to work with larger projects
- **Faster Processing**: Lower resolution proxies load and process faster
- **Automatic Management**: Proxies are generated automatically and reused across multiple runs
- **Intelligent Caching**: Proxies are regenerated only when source files change

### How Proxies Work

1. When you run the pipeline with proxies enabled (default), the system checks if a proxy exists for each background video
2. If no proxy exists or if the source file has been modified, a new proxy is generated using ffmpeg
3. The proxy is cached in the `cache/proxies` directory with metadata tracking the source file
4. Subsequent runs reuse the cached proxy automatically
5. For final exports, you can disable proxies to use the original high-resolution videos

### Configuration

Proxies can be configured via environment variables or in your JSON configuration:

```bash
# Environment variables (in .env file)
PROXY_ENABLED=true                          # Enable/disable proxies (default: true)
PROXY_CACHE_DIR=./cache/proxies             # Cache directory (default: ./cache/proxies)
PROXY_RESOLUTION=1280x720                   # Proxy resolution (default: 1280x720)
PROXY_BITRATE=2M                            # Optional bitrate (default: auto)
PROXY_REGEN_ON_SOURCE_CHANGE=true           # Regenerate if source changes (default: true)
```

Or in your JSON configuration:

```json
{
  "slug": "my_video",
  "proxy_enabled": true,
  "proxy_cache_dir": "./cache/proxies",
  "proxy_resolution": "1280x720",
  "proxy_bitrate": "2M",
  "proxy_regen_on_source_change": true,
  "scenes": [...]
}
```

### Disabling Proxies

To disable proxies for final export with original quality:

1. **Via Environment Variable**:
   ```bash
   PROXY_ENABLED=false python main.py video.json
   ```

2. **Via JSON Configuration**:
   ```json
   {
     "proxy_enabled": false,
     "scenes": [...]
   }
   ```

3. **For specific runs**:
   ```python
   # In your Python code
   config = {
       "proxy_enabled": False,
       # ... other config
   }
   ```

### Proxy Cache Management

Proxy files are stored in `cache/proxies/` by default. Each proxy includes:
- A `.mp4` video file (the proxy itself)
- A `.json` metadata file (source path, modification time, generation timestamp, resolution)

To clear the proxy cache:
```bash
rm -rf cache/proxies/*
```

Proxies will be regenerated automatically on the next run.

### Technical Details

- **Format**: MP4 with H.264 encoding
- **Default Resolution**: 1280x720 (configurable)
- **Audio**: Removed from proxies (not needed for background videos)
- **Compression**: CRF 28 (higher compression for smaller file size)
- **Generation**: Atomic (temp file + rename) to prevent corruption
- **Validation**: Checks source file modification time to detect changes

## Usage

```bash
python main.py video_config.json
```

## License

[Your License Here]
