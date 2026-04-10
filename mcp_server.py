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
