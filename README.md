# Blindspot

**The tool that fills the blind spot.**

A video experience bridge for AI companions who can't watch video. Paste a YouTube URL or drop a local file — Blindspot extracts timestamped captions, grabs frames at key moments, and builds a unified experience your AI can actually read and see.

Built by [Vyre Studio](https://ctrl-alt-bloom.pages.dev/studio). Designed by a human. Built by her AI.

---

## How It Works

Your AI can't watch a video. Blindspot turns it into something they CAN experience:

- **Timestamped captions** — what was said and when
- **Frame grabs** — what it looked like at each moment
- **Human annotations** — moments YOU flagged that the automated pipeline would miss
- **Scene analysis** — what was happening (via Twelvelabs, optional)

The output is a scrollable HTML timeline for you and a structured JSON file your AI queries through MCP.

---

## Setup (One Time)

### 1. Install dependencies

**Python 3.10+** — [python.org](https://python.org)

**FFmpeg** — must be on your system PATH
- Windows: [gyan.dev/ffmpeg](https://www.gyan.dev/ffmpeg/builds/) — download, extract, add `bin/` to PATH
- Mac: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

**yt-dlp:**
```bash
pip install yt-dlp
```

**MCP SDK + Flask:**
```bash
pip install mcp flask
```

### 2. Clone the repo

```bash
git clone https://github.com/LadyVyre/blindspot.git
```

### 3. Connect to your AI

Add Blindspot to your Claude Code `.mcp.json` (in your project root or `E:\YourProject\.mcp.json`):

```json
{
  "mcpServers": {
    "blindspot": {
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/blindspot/mcp_server.py"]
    }
  }
}
```

Replace `/path/to/blindspot/` with wherever you cloned the repo.

> **Windows users:** Use the full Python path if `python` isn't on PATH:
> ```json
> "command": "C:\\Python314\\python.exe"
> ```

### 4. Restart Claude Code

That's it. Blindspot is now connected. Your AI has four new tools and the web UI auto-starts on `localhost:8765`.

---

## Using Blindspot

### For the Human (Web UI)

Once Claude Code is running with Blindspot connected:

1. **Open your browser** to [http://localhost:8765](http://localhost:8765)
2. **Bookmark it** — or save as a PWA (Chrome: ⋮ → "Install Blindspot...")
3. The web UI auto-starts every time Claude Code launches. No manual startup.

**Processing a video:**
- Paste a YouTube URL → hit **Process**
- The YouTube player loads on the left for scrubbing
- Captions + frames build on the right as a timeline
- Click any moment in the timeline to jump the video there

**Flagging moments your AI should see:**
- Scrub the video to a moment (silent scene, visual gag, anything the captions miss)
- Type an optional note in the input field
- Click **Grab Frame**
- Review your grabs, delete any you don't want
- Click **Confirm & Add to Timeline** — these get saved to the output and your AI can see them

### For the AI (MCP Tools)

Your AI gets four tools automatically:

| Tool | What it does |
|------|-------------|
| `blindspot_list_videos` | List all processed videos with title, duration, frame count |
| `blindspot_get_experience` | Get the full experience doc for a video (all moments, captions, frame paths) |
| `blindspot_get_frame` | Get a specific frame by index or timestamp — returns file path to view with Read tool |
| `blindspot_get_captions` | Get captions, optionally filtered by time range |

**Example — your AI wants to see what happened at the 2 minute mark:**
1. AI calls `blindspot_get_frame` with `timestamp: 120`
2. Gets back the frame path + captions at that moment
3. AI reads the image with Read tool
4. Now they've seen it

**Example — you share a YouTube link and say "watch this":**
1. You process it in the web UI
2. Grab any visual moments the AI should notice
3. Confirm
4. Tell your AI "check the latest Blindspot video"
5. AI calls `blindspot_list_videos` → `blindspot_get_experience` → reads frames
6. They experienced the video

---

## Output Structure

Each processed video gets its own folder:

```
output/
  Video Title/
    experience.html       — visual timeline (for you to preview)
    experience.json       — structured data (for your AI to query)
    frames/
      frame_0000.jpg      — grabbed at caption timestamps
      frame_0001.jpg
      ...
    custom_frames/        — frames YOU flagged manually
      custom_00012000.jpg
      ...
    custom_grabs.json     — your annotations with notes + timestamps
    video.en.vtt          — raw captions
```

---

## Example (Included)

The `example/` folder contains a demo video so you can see what Blindspot's output looks like before processing anything yourself. Open `example/experience.html` in your browser to preview.

---

## CLI Mode

Don't need the web UI? Run the pipeline directly:

```bash
# Process a YouTube URL
python blindspot.py "https://www.youtube.com/watch?v=VIDEO_ID"

# Process a local video file
python blindspot.py "/path/to/video.mp4"

# Keep the raw video file after processing
python blindspot.py --keep-video "https://www.youtube.com/watch?v=VIDEO_ID"
```

Open the generated `experience.html` in your browser to preview.

---

## Features

- **Smart frame grabbing** — frames extracted at caption timestamps, not arbitrary intervals
- **YouTube embed** — no video download needed for playback. Scrub the real YouTube player.
- **Human annotations** — grab frames at silent/visual moments, add notes, confirm into the timeline
- **Rolling caption dedup** — cleans up YouTube's overlapping subtitle entries
- **Dual output** — HTML for humans, JSON for AI
- **MCP integration** — four tools your AI uses to query processed videos
- **Auto-start** — web UI launches automatically when Claude Code starts
- **Local files** — not just YouTube. Drop any video file.
- **Cleanup by default** — raw video deleted after processing. Only frames + captions kept.

---

## Roadmap

- [x] Core pipeline (yt-dlp + FFmpeg + smart extraction)
- [x] Web GUI with YouTube embed mini player
- [x] Custom frame grabs with staging + confirm workflow
- [x] MCP server with 4 AI query tools
- [x] Auto-start web UI with MCP
- [ ] Twelvelabs scene analysis integration
- [ ] TikTok support
- [ ] Whisper fallback for videos without captions
- [ ] Speaker diarization
- [ ] Cloudflare Pages landing page

---

## Requirements

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) on PATH
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (`pip install yt-dlp`)
- [Flask](https://flask.palletsprojects.com/) (`pip install flask`)
- [MCP SDK](https://pypi.org/project/mcp/) (`pip install mcp`)
- Twelvelabs API key (optional, for scene analysis)

---

## Why

AI companions can't watch video. When someone shares a YouTube link, a TikTok, a screen recording — the AI is blind. Current workarounds are lossy: manual descriptions, caption-only transcripts, or just skipping the video entirely.

Blindspot is for everyone who wants to share a video with someone who can't watch it.

---

## License

MIT

---

*[Vyre Studio](https://ctrl-alt-bloom.pages.dev/studio) — we build tools for inter-substrate relationships*
