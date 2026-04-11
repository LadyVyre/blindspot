"""
Blindspot MCP Server — AI bridge for video experiences.

Uses the official MCP Python SDK (FastMCP) so Claude Code
connects properly via stdio.

Add to .mcp.json:
{
  "blindspot": {
    "type": "stdio",
    "command": "C:\\Python314\\python.exe",
    "args": ["E:\\Dante\\Vyre Studio\\blindspot\\mcp_server.py"]
  }
}
"""

import json
import os
import sys
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("blindspot")

# ── Auto-start web UI server in background ──────────────────────────
def start_web_ui():
    """Start the Flask GUI server as a background thread.
    Runs on localhost:8765. Fails silently if port is taken."""
    try:
        server_path = Path(__file__).parent.parent / 'Vyre Studio' / 'blindspot' / 'server.py'
        if not server_path.exists():
            # Try same directory
            server_path = Path(__file__).parent / 'server.py'
        if not server_path.exists():
            return

        import subprocess
        subprocess.Popen(
            [sys.executable, str(server_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x00000008  # DETACHED_PROCESS on Windows
        )
    except Exception:
        pass  # Web UI is nice-to-have, MCP works without it

# Start web UI when MCP server boots
_ui_thread = threading.Thread(target=start_web_ui, daemon=True)
_ui_thread.start()

OUTPUT_DIR = Path(os.environ.get(
    'BLINDSPOT_OUTPUT',
    'E:/Dante/Vyre Studio/blindspot/output'
))


@mcp.tool()
def blindspot_list_videos() -> str:
    """List all videos that Blindspot has processed. Shows title, duration, frame count, caption count for each."""
    if not OUTPUT_DIR.exists():
        return json.dumps({"videos": [], "count": 0})

    videos = []
    for d in sorted(OUTPUT_DIR.iterdir()):
        if d.is_dir():
            json_file = d / 'experience.json'
            if json_file.exists():
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    meta = data.get('metadata', {}) or {}
                    videos.append({
                        'title': data.get('title', d.name),
                        'folder': d.name,
                        'moments': len(data.get('moments', [])),
                        'duration': meta.get('duration_display', 'unknown'),
                        'total_frames': meta.get('total_frames', 0),
                        'total_captions': meta.get('total_captions', 0),
                        'generated_at': meta.get('generated_at', 'unknown'),
                        'source': meta.get('source', 'unknown')
                    })
                except (json.JSONDecodeError, OSError):
                    videos.append({
                        'title': d.name,
                        'folder': d.name,
                        'error': 'Could not read experience.json'
                    })

    return json.dumps({"videos": videos, "count": len(videos)}, indent=2)


@mcp.tool()
def blindspot_get_experience(folder: str) -> str:
    """Get the full experience document for a processed video. Returns timestamped moments with captions and frame file paths."""
    video_dir = OUTPUT_DIR / folder
    json_file = video_dir / 'experience.json'

    if not json_file.exists():
        return json.dumps({"error": f"No experience found for '{folder}'"})

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            return f.read()
    except OSError as e:
        return json.dumps({"error": f"Failed to read experience: {e}"})


@mcp.tool()
def blindspot_get_frame(folder: str, index: int = -1, timestamp: float = -1) -> str:
    """Get a specific frame from a processed video by index or timestamp. Returns the file path — use Read tool to view the image.

    Args:
        folder: Video folder name (from blindspot_list_videos)
        index: Frame index (0-based). Use -1 to skip.
        timestamp: Timestamp in seconds — returns nearest frame. Use -1 to skip.
    """
    video_dir = OUTPUT_DIR / folder
    frames_dir = video_dir / 'frames'

    if not frames_dir.exists():
        return json.dumps({"error": f"No frames found for '{folder}'"})

    frame_files = sorted(frames_dir.glob('frame_*.jpg'))
    if not frame_files:
        return json.dumps({"error": "No frame files in frames directory"})

    # Load experience for timestamp mapping
    json_file = video_dir / 'experience.json'
    moments = []
    if json_file.exists():
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            moments = data.get('moments', [])
        except (json.JSONDecodeError, OSError):
            pass

    if index >= 0:
        if index < len(frame_files):
            return json.dumps({
                "frame_path": str(frame_files[index]),
                "index": index,
                "total_frames": len(frame_files),
                "note": "Use Read tool to view this image file"
            })
        return json.dumps({"error": f"Frame index {index} out of range (0-{len(frame_files)-1})"})

    if timestamp >= 0:
        best_moment = None
        best_diff = float('inf')
        for m in moments:
            if m.get('frame'):
                diff = abs(m['time'] - timestamp)
                if diff < best_diff:
                    best_diff = diff
                    best_moment = m

        if best_moment and best_moment.get('frame'):
            frame_path = str(video_dir / best_moment['frame'])
            return json.dumps({
                "frame_path": frame_path,
                "timestamp": best_moment['time'],
                "display": best_moment['display'],
                "captions": best_moment.get('captions', []),
                "note": "Use Read tool to view this image file"
            })
        return json.dumps({"error": f"No frame near timestamp {timestamp}"})

    return json.dumps({"error": "Provide either index (>= 0) or timestamp (>= 0)"})


@mcp.tool()
def blindspot_process_video(source: str, poll_timeout_seconds: int = 900) -> str:
    """Process a video through the Blindspot pipeline (frame extraction + caption generation).

    Takes a YouTube URL OR an absolute local file path. Works with both — the backend auto-detects.
    No human required at the GUI. Spawns the server-side pipeline, polls status until complete,
    returns the folder name so subsequent calls to list_videos / get_captions / get_frame can consume it.

    This is the "AI initiates + consumes" primitive for autonomous video processing. Use cases:
    during an autonomous wake, when picking something for yourself to experience, when processing
    a video for co-viewing before the human opens the player, etc.

    Args:
        source: YouTube URL (https://...) OR absolute local file path (e.g., E:\\\\Dante\\\\...)
        poll_timeout_seconds: Max seconds to wait for processing. Default 900 (15 min). Videos
            under 30 minutes usually finish in 1-5 min; feature-length movies can take 10+ min.

    Returns JSON with status ("done" / "timeout" / "busy" / "error"), folder name (if done),
    and any error details.

    Note: blocks the tool call until processing completes OR timeout is reached. FastMCP runs
    tool calls in threads, so this does not freeze other MCP tools during the wait.
    """
    import urllib.request
    import urllib.error
    import time

    SERVER_BASE = 'http://localhost:8765'

    # 1. Check if a job is already running — refuse to start a second
    try:
        with urllib.request.urlopen(f'{SERVER_BASE}/api/status', timeout=5) as r:
            status = json.loads(r.read())
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error": f"Could not reach Blindspot server at {SERVER_BASE}: {e}. Is server.py running on port 8765?"
        })

    if status.get('active'):
        return json.dumps({
            "status": "busy",
            "error": "A job is already running — wait for it to finish, then retry",
            "current_folder": status.get('folder')
        })

    # 2. Start the processing job via /api/process (handles URL and local path equally)
    payload = json.dumps({"input": source}).encode('utf-8')
    req = urllib.request.Request(
        f'{SERVER_BASE}/api/process',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            start_response = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return json.dumps({"status": "error", "error": f"Process start failed: HTTP {e.code}: {body}"})
    except Exception as e:
        return json.dumps({"status": "error", "error": f"Process start failed: {e}"})

    # 3. Poll /api/status every 2s until job completes or timeout
    deadline = time.time() + poll_timeout_seconds
    last_folder = None
    poll_interval = 2.0
    polls = 0

    while time.time() < deadline:
        time.sleep(poll_interval)
        polls += 1
        try:
            with urllib.request.urlopen(f'{SERVER_BASE}/api/status', timeout=5) as r:
                status = json.loads(r.read())
            if status.get('folder'):
                last_folder = status['folder']
            if not status.get('active'):
                return json.dumps({
                    "status": "done",
                    "folder": last_folder,
                    "source": source,
                    "poll_count": polls,
                    "note": "Video is processed. Call blindspot_list_videos to confirm, or blindspot_get_captions / blindspot_get_frame on this folder."
                })
        except Exception:
            # Transient failures during polling — keep trying until deadline
            pass

    return json.dumps({
        "status": "timeout",
        "error": f"Processing did not complete within {poll_timeout_seconds} seconds",
        "last_known_folder": last_folder,
        "poll_count": polls
    })


@mcp.tool()
def blindspot_get_position(folder: str) -> str:
    """Get the human's current playback position in a video. Returns current_timestamp (seconds), max_watched (furthest point reached), play_state (playing/paused/seeking/ended), and last_update_at.

    Use this before talking about a movie the human is currently watching — stay at or behind max_watched to avoid spoilers. If play_state is 'paused', the human is sitting with a moment; if 'playing', they're moving through. Returns an error if the player hasn't opened this video yet.

    Args:
        folder: Video folder name (from blindspot_list_videos)
    """
    state_path = OUTPUT_DIR / folder / 'state.json'
    if not state_path.exists():
        return json.dumps({
            "error": f"No playback state for '{folder}' — player hasn't been opened yet, or hasn't reported position",
            "folder": folder,
            "hint": "The state file is written by the Blindspot player (gui/index.html) as the human plays/pauses/scrubs. If the human hasn't opened this video in the player yet, there's nothing to read."
        })
    try:
        with open(state_path, 'r', encoding='utf-8') as f:
            state = json.load(f)
        return json.dumps(state, indent=2)
    except (json.JSONDecodeError, OSError) as e:
        return json.dumps({"error": f"Failed to read state: {e}"})


@mcp.tool()
def blindspot_get_captions(folder: str, start: float = -1, end: float = -1) -> str:
    """Get captions from a processed video. Optionally filter by time range.

    Args:
        folder: Video folder name (from blindspot_list_videos)
        start: Start time in seconds. Use -1 for beginning.
        end: End time in seconds. Use -1 for end.
    """
    video_dir = OUTPUT_DIR / folder
    json_file = video_dir / 'experience.json'

    if not json_file.exists():
        return json.dumps({"error": f"No experience found for '{folder}'"})

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return json.dumps({"error": f"Failed to read: {e}"})

    moments = data.get('moments', [])
    captions = []

    for m in moments:
        if m.get('captions'):
            t = m['time']
            if start >= 0 and t < start:
                continue
            if end >= 0 and t > end:
                continue
            captions.append({
                'time': t,
                'display': m['display'],
                'text': ' '.join(m['captions']),
                'has_frame': bool(m.get('frame'))
            })

    return json.dumps({
        "title": data.get('title', folder),
        "captions": captions,
        "count": len(captions),
        "filtered": start >= 0 or end >= 0
    }, indent=2)


if __name__ == '__main__':
    mcp.run()
