#!/usr/bin/env python3
# kinescope-dl
# Usage: python3 kinescope-dl.py <video-id> [video-name]
# Requires: xmltodict, ffmpeg

import os
import subprocess
import sys
import urllib.parse
import urllib.request

import xmltodict

BASEURL = "https://kinescope.io"
REFERER = "https://kinescope.io"
AUDIO_CHUNK_SEGMENTS = 200
VIDEO_CHUNK_SEGMENTS = 100
SAFE_CHUNK_LEN = 24_000_000


def err_exit(msg):
    raise SystemExit(f"Error: {msg}")


def http_get(url, byte_range=None):
    req = urllib.request.Request(url)
    req.add_header("Referer", REFERER)
    if byte_range:
        req.add_header("Range", f"bytes={byte_range}")
    return urllib.request.urlopen(req).read()


def as_list(x):
    """xmltodict returns a dict for a single child and a list for multiple — normalize."""
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def download_stream(base_url, init_source_url, init_range, segments, chunk_size, label):
    """
    Download an init segment + all media segments for one Representation.
    Returns the concatenated bytes.

    base_url        — the <BaseURL> for this Representation. May be a directory
                      (ending in /) or a full file URL (e.g. .../audio_0.mp4).
    init_source_url — value of Initialization/@sourceURL. May be empty when the
                      BaseURL itself is the media file (audio case).
    init_range      — byte range for the init segment.
    segments        — list of <SegmentURL> dicts (each has @mediaRange and
                      optionally @media).
    """
    # Resolve init segment URL
    if init_source_url:
        init_url = urllib.parse.urljoin(base_url, init_source_url)
    else:
        init_url = base_url  # audio case: BaseURL is the file

    print(f"  Init segment: {init_url} bytes={init_range}")
    data = http_get(init_url, init_range)

    total = len(segments)
    i = 0
    while i < total:
        seg = segments[i]
        media_attr = seg.get("@media", "")
        seg_url = urllib.parse.urljoin(base_url, media_attr) if media_attr else base_url

        from_b = int(seg["@mediaRange"].split("-")[0])
        chunk_start = i

        # Greedily extend the chunk while next segment shares the URL and stays under SAFE_CHUNK_LEN
        while i < total and i < chunk_start + chunk_size:
            cur_media = segments[i].get("@media", "")
            cur_url = urllib.parse.urljoin(base_url, cur_media) if cur_media else base_url
            if cur_url != seg_url:
                break
            cur_to = int(segments[i]["@mediaRange"].split("-")[1])
            if cur_to - from_b + 1 > SAFE_CHUNK_LEN:
                break
            i += 1

        to_b = int(segments[i - 1]["@mediaRange"].split("-")[1])
        pct = i / total * 100
        print(
            f"  {label}: {i}/{total} ({pct:5.1f}%)  "
            f"bytes={from_b}-{to_b}  size={to_b - from_b + 1}",
            end="\r",
        )
        sys.stdout.flush()
        data += http_get(seg_url, f"{from_b}-{to_b}")

    print()
    return data


def pick_video_representation(adaptation_set):
    """Pick the highest-resolution Representation."""
    reps = as_list(adaptation_set["Representation"])
    return max(reps, key=lambda r: int(r["@width"]))


def main():
    if len(sys.argv) < 2:
        err_exit("Usage: kinescope-dl.py <video-id> [video-name]")

    video_id = sys.argv[1]
    video_name = sys.argv[2] if len(sys.argv) > 2 else video_id

    baseurl = os.environ.get("BASEURL", BASEURL)

    print(f"Fetching manifest: {baseurl}/{video_id}/master.mpd")
    mpd_raw = http_get(f"{baseurl}/{video_id}/master.mpd")
    mpd = xmltodict.parse(mpd_raw)

    adaptations = as_list(mpd["MPD"]["Period"]["AdaptationSet"])

    # Identify video and audio adaptation sets by mimeType (don't trust ordering)
    video_set = next((a for a in adaptations if a.get("@mimeType", "").startswith("video/")), None)
    audio_set = next((a for a in adaptations if a.get("@mimeType", "").startswith("audio/")), None)

    if video_set is None or audio_set is None:
        err_exit("Could not find both video and audio adaptation sets in the manifest")

    # ---- Video ----
    video_rep = pick_video_representation(video_set)
    print(f"\nVideo: {video_rep['@width']}x{video_rep['@height']} "
          f"@ {int(video_rep['@bandwidth']) // 1000} kbps")
    v_base = video_rep["BaseURL"]
    v_seglist = video_rep["SegmentList"]
    v_init = v_seglist["Initialization"]
    v_segments = as_list(v_seglist["SegmentURL"])

    video_data = download_stream(
        base_url=v_base,
        init_source_url=v_init.get("@sourceURL", ""),
        init_range=v_init["@range"],
        segments=v_segments,
        chunk_size=VIDEO_CHUNK_SEGMENTS,
        label="Video",
    )

    video_tmp = f"{video_id}.video"
    with open(video_tmp, "wb") as f:
        f.write(video_data)
    print(f"Video stream saved ({len(video_data):,} bytes)\n")

    # ---- Audio ----
    audio_rep = as_list(audio_set["Representation"])[0]
    print(f"Audio: {int(audio_rep['@bandwidth']) // 1000} kbps")
    a_base = audio_rep["BaseURL"]
    a_seglist = audio_rep["SegmentList"]
    a_init = a_seglist["Initialization"]
    a_segments = as_list(a_seglist["SegmentURL"])

    audio_data = download_stream(
        base_url=a_base,
        init_source_url=a_init.get("@sourceURL", ""),
        init_range=a_init["@range"],
        segments=a_segments,
        chunk_size=AUDIO_CHUNK_SEGMENTS,
        label="Audio",
    )

    audio_tmp = f"{video_id}.audio"
    with open(audio_tmp, "wb") as f:
        f.write(audio_data)
    print(f"Audio stream saved ({len(audio_data):,} bytes)\n")

    # ---- Mux ----
    out = f"{video_name}.mp4"
    print(f"Muxing into {out}...")
    cmd = ["ffmpeg", "-y", "-i", video_tmp, "-i", audio_tmp, "-c", "copy", out]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode:
        err_exit(f"ffmpeg failed:\n{res.stderr.decode()}")

    os.unlink(video_tmp)
    os.unlink(audio_tmp)
    print(f"Done: {out}")


if __name__ == "__main__":
    main()