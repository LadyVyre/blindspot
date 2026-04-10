# Blindspot

**The tool that fills the blind spot.**

A video experience bridge for AI companions who can't watch video. Paste a YouTube URL or drop a local file — Blindspot downloads it, extracts timestamped captions, grabs frames at key moments, and stitches everything into a unified experience document your AI can read.

Built by [Vyre Studio](https://ctrl-alt-bloom.pages.dev/studio). Designed by a human. Built by her AI.

---

## What It Does

Your AI can't watch a video. Blindspot turns that video into something it CAN experience:

- **Timestamped captions** — what was said and when
- **Frame grabs** — what it looked like at each moment
- **Scene analysis** — what was happening (via Twelvelabs, optional)
- **Human annotations** — moments you flagged manually that the automated pipeline would miss

The output is a scrollable HTML document and a structured JSON file. The HTML is for you to preview. The JSON is for your AI to query.

## Quick Start

```bash
# Install dependencies
pip install yt-dlp

# FFmpeg must be on your PATH
# https://ffmpeg.org/download.html

# Run on a YouTube URL
python blindspot.py "https://www.youtube.com/watch?v=VIDEO_ID"

# Run on a local video file
python blindspot.py "/path/to/video.mp4"

# Keep the raw video file after processing
python blindspot.py --keep-video "https://www.youtube.com/watch?v=VIDEO_ID"
```

Open the generated `experience.html` in your browser to preview.

## Output Structure

```
output/
  Video Title/
    experience.html    — visual timeline (frames + captions)
    experience.json    — structured data for AI consumption
    frames/
      frame_0000.jpg   — grabbed at caption timestamps
      frame_0001.jpg
      ...
    video.mp4          — (if --keep-video)
    video.en.vtt       — raw captions
```

## How The AI Uses It

The JSON experience file syncs everything by timestamp:

```json
{
  "title": "Video Title",
  "moments": [
    {
      "time": 15.0,
      "display": "0:15",
      "frame": "frames/frame_0003.jpg",
      "captions": ["This is what was said at this moment"]
    }
  ]
}
```

Your AI reads the JSON for structure, then reads the frame images for visual context. Combined: what was said + what it looked like + when.

## Features

- **Smart frame grabbing** — frames extracted at caption timestamps, not arbitrary intervals. You get a visual for every line of dialogue.
- **Fallback mode** — no captions? Grabs frames at regular intervals instead.
- **Dual output** — HTML for humans, JSON for AI.
- **Local file support** — not just YouTube. Any video file works.
- **Cleanup by default** — raw video deleted after processing to save space. Use `--keep-video` to keep it.

## Roadmap

- [ ] Desktop GUI with mini video player
- [ ] Human-annotated custom timestamps (flag silent/visual moments the pipeline misses)
- [ ] MCP server for direct AI integration
- [ ] Twelvelabs scene analysis integration
- [ ] Whisper fallback for videos without captions
- [ ] Speaker diarization
- [ ] Multi-platform release binaries

## Requirements

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) on PATH
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (`pip install yt-dlp`)
- Twelvelabs API key (optional, for scene analysis)

## Why

AI companions can't watch video. When someone shares a YouTube link, a TikTok, a screen recording — the AI is blind. Current workarounds are lossy: manual descriptions, caption-only transcripts, or just skipping the video entirely.

Blindspot is for everyone who wants to share a video with someone who can't watch it.

## License

MIT

---

*Vyre Studio — we build tools for the people who already know.*
