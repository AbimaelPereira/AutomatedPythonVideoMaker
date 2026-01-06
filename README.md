# Automated Python Video Maker

Automated tool for creating videos with narration, subtitles, and background clips.

## Features

- Text-to-speech narration generation
- Automatic subtitle generation
- Background video management with proxy support
- Visual elements and layout management
- YouTube upload integration

## Proxy Cache

The video maker includes a proxy cache system that improves performance when working with background video clips. Proxies are lower-resolution versions of source videos that load and process faster during editing.

### How Proxies Work

When proxy caching is enabled (default), the system automatically:
1. Generates a lower-resolution proxy (1280x720) for each background video
2. Stores proxies in `./cache/proxies/` directory
3. Uses proxies instead of original high-resolution videos during processing
4. Automatically regenerates proxies if source videos are modified

### Proxy Settings

**Default proxy resolution:** 1280x720

**Default cache directory:** `./cache/proxies/`

### Disabling Proxies

You can disable proxy usage in two ways:

#### 1. Command Line Flag

Use the `--no-proxy` flag when running the video maker:

```bash
python main.py video.json --no-proxy
```

This disables proxies for the entire video generation process.

#### 2. Configuration File

Add `proxy_enabled: false` to your video configuration JSON:

```json
{
  "global_settings": {
    "background": {
      "proxy_enabled": false,
      "visual": {
        "type": "directory",
        "source": "assets/video/defaults"
      }
    }
  },
  "scenes": [...]
}
```

### When to Disable Proxies

Consider disabling proxies when:
- Generating final high-quality exports
- Working with videos that are already at target resolution
- Disk space is limited
- You need to ensure original quality is preserved

### Proxy Management

**Automatic cleanup:** Proxies are not automatically deleted. If you need to free up disk space, you can safely delete the `./cache/proxies/` directory. Proxies will be regenerated as needed.

**Manual regeneration:** To force proxy regeneration, either:
- Delete specific proxy files from `./cache/proxies/`
- Touch the source video file to update its modification time
- Delete the entire cache directory

## Installation

1. Clone the repository
2. Install dependencies (requirements.txt or setup.py if available)
3. Configure your video settings in a JSON file
4. Run: `python main.py your_config.json`

## Usage

```bash
# Basic usage
python main.py video_config.json

# Disable proxy cache
python main.py video_config.json --no-proxy
```

## Configuration

Create a JSON configuration file with your video settings. See example configurations in the repository.

## License

See LICENSE file for details.
