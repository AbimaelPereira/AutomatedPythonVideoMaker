# Automated Python Video Maker

## Proxy-based Background Video Processing

This system includes a proxy cache feature that significantly reduces memory usage when processing background videos. Proxies are low-resolution, lower-bitrate copies of background videos that are automatically generated and cached on disk.

### Features

- **Automatic proxy generation**: Proxies are created on-demand when processing videos
- **Smart caching**: Proxies are reused across video generations
- **Invalidation**: Proxies are automatically regenerated when source videos change
- **Configurable**: Enable/disable proxies and configure resolution, bitrate, and cache location
- **Memory efficient**: Can reduce peak memory usage by >40% for large video jobs

### Configuration

Proxy settings can be configured via environment variables or in the video JSON configuration:

#### Environment Variables

```bash
# Enable/disable proxy usage (default: true)
PROXY_ENABLED=true

# Proxy resolution (default: "1280x720")
PROXY_RESOLUTION="1280x720"

# Proxy bitrate (optional, let ffmpeg decide if not set)
PROXY_BITRATE="2M"

# Proxy cache directory (default: "./cache/proxies")
PROXY_CACHE_DIR="./cache/proxies"

# Regenerate proxy when source changes (default: true)
PROXY_REGEN_ON_SOURCE_CHANGE=true
```

#### JSON Configuration

You can also set these options in your video JSON file:

```json
{
  "slug": "my-video",
  "proxy_enabled": true,
  "proxy_resolution": "1280x720",
  "proxy_cache_dir": "./cache/proxies",
  "scenes": [...]
}
```

### Command Line Usage

#### View Proxy Cache Statistics

```bash
python3 main.py test.json --proxy-stats
```

This will display:
- Whether proxies are enabled
- Cache directory location
- Number of cached proxy files
- Total cache size in MB

#### Disable Proxies for a Single Run

```bash
python3 main.py test.json --no-proxy
```

This bypasses proxy generation and uses original high-resolution videos. Useful for final high-quality exports.

### How It Works

1. **First Run**: When processing a background video for the first time:
   - A proxy is generated using ffmpeg with reduced resolution and bitrate
   - The proxy is saved to the cache directory with a unique name
   - Metadata is saved alongside the proxy (source path, mtime, etc.)
   - The proxy is used for video processing

2. **Subsequent Runs**: When the same background video is processed again:
   - The system checks if a valid proxy exists in cache
   - If the proxy exists and the source hasn't changed, it's reused
   - If the source has changed, a new proxy is generated

3. **Memory Benefits**: 
   - Smaller video files consume less memory when loaded
   - Faster to load and process
   - Significant reduction in peak memory usage for projects with many/large videos

### Cache Management

The proxy cache is stored in `./cache/proxies` by default. This directory contains:
- `.mp4` files: The proxy videos
- `.mp4.meta.json` files: Metadata about each proxy

The cache directory is excluded from git (see `.gitignore`).

To clear the cache, simply delete the cache directory:

```bash
rm -rf ./cache/proxies
```

### Performance Considerations

- **Resolution**: Lower proxy resolution = more memory savings but slightly lower output quality
- **Bitrate**: Lower bitrate = smaller files and faster processing
- **Trade-offs**: For final exports, consider using `--no-proxy` to ensure maximum quality

### Testing

The proxy system includes comprehensive tests:

```bash
# Unit tests for ProxyCache
python3 -m unittest tests.test_proxy_cache -v

# Integration tests
python3 tests/test_integration.py
```

### Technical Details

- **Proxy Generation**: Uses ffmpeg with `scale` filter to maintain aspect ratio
- **Atomic Writes**: Proxies are written to temp files and atomically renamed
- **Invalidation**: Based on source file modification time (mtime)
- **Thread Safety**: Each proxy has a unique filename based on source path hash

### Troubleshooting

**Proxies not being generated?**
- Check that ffmpeg is installed: `ffmpeg -version`
- Check that `proxy_enabled` is `true`
- Check permissions on the cache directory

**Out of disk space?**
- Check cache size: `python3 main.py test.json --proxy-stats`
- Clear old proxies: `rm -rf ./cache/proxies/*`

**Proxies regenerating unnecessarily?**
- Set `proxy_regen_on_source_change=false` to disable mtime checking
