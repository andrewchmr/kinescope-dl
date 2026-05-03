# kinescope-dl

Python script for downloading Kinescope videos. Combines the highest-resolution video stream with the audio stream into an MP4 using ffmpeg.

## Requirements

- Python 3.9+
- ffmpeg available on PATH
- `xmltodict`

## Install

```bash
git clone https://github.com/andrewchmr/kinescope-dl.git
cd kinescope-dl

pip install xmltodict
brew install ffmpeg          # macOS
# sudo apt install ffmpeg    # Debian/Ubuntu
```

## Usage

```bash
python3 kinescope_dl.py  [output-name]
```

**Finding the video ID:** open the page with the video, open DevTools → Network, filter for `master.mpd`, and take the path segment before `/master.mpd`. For an iframe URL like `https://kinescope.io/embed/{id}`.

```bash
# Output: {id}.mp4
python3 kinescope_dl.py {id}

# Output: lecture-01.mp4
python3 kinescope_dl.py {id} lecture-01
```

### Environment variables

| Variable               | Default                | Purpose                                             |
| ---------------------- | ---------------------- | --------------------------------------------------- |
| `BASEURL`              | `https://kinescope.io` | Override if Kinescope serves under a different host |
| `REFERER`              | `https://kinescope.io` | Some videos require the embedding site as referer   |
| `AUDIO_CHUNK_SEGMENTS` | `200`                  | Segments per HTTP range request (audio)             |
| `VIDEO_CHUNK_SEGMENTS` | `100`                  | Segments per HTTP range request (video)             |
| `SAFE_CHUNK_LEN`       | `24000000`             | Maximum bytes per range request                     |
