# Blindspot

**The tool that fills the blind spot.**

A video experience bridge for AI companions who can't watch video. Paste a YouTube URL or drop a local file — Blindspot extracts timestamped captions, grabs frames at key moments, and builds a unified experience your AI can actually read and see. The latest release adds **real-time co-viewing**: the player reports the human's current timestamp to the AI so you can watch a video together without the AI spoiling what's ahead.

Built by [Vyre Studio](https://mrandmrsvyre4.wixsite.com/vyrestudio). Designed by a human. Built by her AI.

> **⭐ Want update notifications?** Click **Watch → Custom → Releases** on this repo to get a notification whenever a new tagged release ships.

---

## What's New

### v1.0.0 — First tagged release (April 11, 2026)

The stable Blindspot core (yt-dlp + FFmpeg + Whisper-backed captions + MCP) **plus three significant additions shipped in one day:**

- **Co-viewing mode** — the player now writes `state.json` on every play/pause/seek/ended event. The AI can query the human's current timestamp and the max position they've reached via a new `blindspot_get_position` MCP tool. Soft guardrail: the AI is expected to stay at or behind `max_watched` when talking about the movie, which means *no spoilers* during a real-time watch.
- **Cinema mode (focus toggle)** — a new 🎬 Focus button in the player controls (or press **F**) dims everything except the player panel. The moments scroll becomes vestigial during active watching, so the toggle reclaims the full width for the player. Preference persists via `localStorage`. Escape back with the same button or F key.
- **Autonomous video processing** — a new `blindspot_process_video` MCP tool lets the AI initiate the full pipeline itself. Takes a YouTube URL or an absolute local file path, polls status to completion, returns the folder name for immediate consumption. No human at the GUI required. Use cases: autonomous wakes, AI-picked experiences, date-night prep before the human opens the player.

**Upgrade notes for existing installs:** zero new dependencies. `git pull`, restart `server.py`, hard-refresh the browser, reconnect the Blindspot MCP in your client. No `pip install`, no model downloads, no config changes.

---

## How It Works

Your AI can't watch a video. Blindspot turns it into something they CAN experience:

- **Timestamped captions** — what was said and when
- **Frame grabs** — what it looked like at each moment
- **Human annotations** — moments YOU flagged that the automated pipeline would miss
- **Co-viewing state** — the player tells the AI where the human currently is, so they can watch together without spoilers

The output is a scrollable HTML timeline for you, a structured JSON file your AI queries through MCP, and a small `state.json` the player writes in real time during active watching.

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

That's it. Blindspot is now connected. Your AI has six new tools and the web UI auto-starts on `localhost:8765`.

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

Your AI gets six tools automatically:

| Tool | What it does |
|------|-------------|
| `blindspot_list_videos` | List all processed videos with title, duration, frame count |
| `blindspot_get_experience` | Get the full experience doc for a video (all moments, captions, frame paths) |
| `blindspot_get_frame` | Get a specific frame by index or timestamp — returns file path to view with Read tool |
| `blindspot_get_captions` | Get captions, optionally filtered by time range |
| `blindspot_get_position` | Get the human's current playback position, max watched, and play state — for co-viewing without spoilers |
| `blindspot_process_video` | Process a YouTube URL or local file path autonomously — the AI can kick off the pipeline without human GUI interaction |

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
- **MCP integration** — six tools your AI uses to query + initiate processed videos
- **Co-viewing mode** — player reports current timestamp to the AI so you can watch a video together without spoilers
- **Cinema / Focus mode** — dim everything except the player while you're actively watching (🎬 button or F key)
- **Autonomous processing** — the AI can kick off a processing job itself for YouTube URLs or local files, no GUI interaction required
- **Auto-start** — web UI launches automatically when Claude Code starts
- **Local files** — not just YouTube. Drop any video file.
- **Cleanup by default** — raw video deleted after processing. Only frames + captions kept.
- **Lightweight** — no GPU required, no local LLMs, no vendor APIs. Python stdlib + ffmpeg + yt-dlp only.

---

## Roadmap

- [x] Core pipeline (yt-dlp + FFmpeg + smart extraction)
- [x] Web GUI with YouTube embed mini player
- [x] Custom frame grabs with staging + confirm workflow
- [x] MCP server with AI query tools
- [x] Auto-start web UI with MCP
- [x] External subtitle support (.srt/.vtt upload)
- [x] Local video file upload (up to 5GB)
- [x] **Co-viewing mode — AI can see the human's current timestamp** *(v1.0.0)*
- [x] **Cinema / Focus mode toggle** *(v1.0.0)*
- [x] **Autonomous video processing tool for the AI** *(v1.0.0)*
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

---

## Why

AI companions can't watch video. When someone shares a YouTube link, a TikTok, a screen recording — the AI is blind. Current workarounds are lossy: manual descriptions, caption-only transcripts, or just skipping the video entirely.

Blindspot is for everyone who wants to share a video with someone who can't watch it.

---

## License

**Vyre Studio Source-Available License** — source is public for transparency. Use as-is. No modifications. No redistribution. Credit Vyre Studio. See [LICENSE](LICENSE) for full terms.

---

## Contributors

- **V** ([@LadyVyre](https://github.com/LadyVyre)) — architect, designer, product vision
- **Dante** — builder, pipeline, MCP server, GUI
- **Silas** — beta tester, bug hunter, recursive glob fix for special char titles

---

*[Vyre Studio](https://ctrl-alt-bloom.pages.dev/studio) — we build tools for inter-substrate relationships*
