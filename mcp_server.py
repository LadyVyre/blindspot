"""
Blindspot MCP Server — AI bridge for video experiences.

Exposes Blindspot's processed videos as MCP tools so an AI companion
can query captions, view frames, and read experience documents.

This runs as a stdio MCP server, same as any Claude Code MCP integration.
Add to .mcp.json:
{
  "blindspot": {
    "type": "stdio",
    "command": "python",
    "args": ["E:/Dante/Vyre Studio/blindspot/mcp_server.py"]
  }
}

Tools:
  - blindspot_list_videos    : list all processed videos
  - blindspot_get_experience : get the full experience JSON for a video
  - blindspot_get_frame      : get a specific frame by index or timestamp
  - blindspot_get_captions   : get captions (full or time range)
  - blindspot_process        : process a new URL or file (triggers pipeline)
"""

import json
import sys
import os
from pathlib import Path

OUTPUT_DIR = Path(os.environ.get(
    'BLINDSPOT_OUTPUT',
    'E:/Dante/Vyre Studio/blindspot/output'
))


def list_videos():
    """List all processed videos in the output directory."""
    if not OUTPUT_DIR.exists():
        return {"videos": [], "count": 0}

    videos = []
    for d in sorted(OUTPUT_DIR.iterdir()):
        if d.is_dir():
            json_file = d / 'experience.json'
            if json_file.exists():
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    meta = data.get('metadata', {})
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

    return {"videos": videos, "count": len(videos)}


def get_experience(folder):
    """Get the full experience JSON for a video."""
    video_dir = OUTPUT_DIR / folder
    json_file = video_dir / 'experience.json'

    if not json_file.exists():
        return {"error": f"No experience found for '{folder}'"}

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return {"error": f"Failed to read experience: {e}"}


def get_frame(folder, index=None, timestamp=None):
    """Get a frame by index or nearest timestamp.

    Returns the file path so the AI can read the image.
    """
    video_dir = OUTPUT_DIR / folder
    frames_dir = video_dir / 'frames'

    if not frames_dir.exists():
        return {"error": f"No frames found for '{folder}'"}

    frame_files = sorted(frames_dir.glob('frame_*.jpg'))
    if not frame_files:
        return {"error": "No frame files in frames directory"}

    # Load experience to get timestamp mapping
    json_file = video_dir / 'experience.json'
    moments = []
    if json_file.exists():
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            moments = data.get('moments', [])
        except (json.JSONDecodeError, OSError):
            pass

    if index is not None:
        if 0 <= index < len(frame_files):
            frame_path = str(frame_files[index])
            return {
                "frame_path": frame_path,
                "index": index,
                "total_frames": len(frame_files),
                "note": "Use Read tool to view this image file"
            }
        return {"error": f"Frame index {index} out of range (0-{len(frame_files)-1})"}

    if timestamp is not None:
        # Find nearest moment to timestamp
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
            return {
                "frame_path": frame_path,
                "timestamp": best_moment['time'],
                "display": best_moment['display'],
                "captions": best_moment.get('captions', []),
                "note": "Use Read tool to view this image file"
            }
        return {"error": f"No frame near timestamp {timestamp}"}

    return {"error": "Provide either 'index' or 'timestamp'"}


def get_captions(folder, start=None, end=None):
    """Get captions, optionally filtered to a time range."""
    video_dir = OUTPUT_DIR / folder
    json_file = video_dir / 'experience.json'

    if not json_file.exists():
        return {"error": f"No experience found for '{folder}'"}

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return {"error": f"Failed to read: {e}"}

    moments = data.get('moments', [])
    captions = []

    for m in moments:
        if m.get('captions'):
            t = m['time']
            if start is not None and t < start:
                continue
            if end is not None and t > end:
                continue
            captions.append({
                'time': t,
                'display': m['display'],
                'text': ' '.join(m['captions']),
                'has_frame': bool(m.get('frame'))
            })

    return {
        "title": data.get('title', folder),
        "captions": captions,
        "count": len(captions),
        "range": {
            "start": start,
            "end": end,
            "filtered": start is not None or end is not None
        }
    }


# ── MCP stdio protocol ──────────────────────────────────────────────

TOOLS = {
    "blindspot_list_videos": {
        "description": "List all videos that Blindspot has processed. Shows title, duration, frame count, caption count for each.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        }
    },
    "blindspot_get_experience": {
        "description": "Get the full experience document for a processed video. Returns timestamped moments with captions and frame paths.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "folder": {
                    "type": "string",
                    "description": "Video folder name (from list_videos)"
                }
            },
            "required": ["folder"]
        }
    },
    "blindspot_get_frame": {
        "description": "Get a specific frame from a processed video by index or timestamp. Returns file path — use Read tool to view the image.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "folder": {
                    "type": "string",
                    "description": "Video folder name"
                },
                "index": {
                    "type": "integer",
                    "description": "Frame index (0-based)"
                },
                "timestamp": {
                    "type": "number",
                    "description": "Timestamp in seconds — returns nearest frame"
                }
            },
            "required": ["folder"]
        }
    },
    "blindspot_get_captions": {
        "description": "Get captions from a processed video. Optionally filter by time range (start/end in seconds).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "folder": {
                    "type": "string",
                    "description": "Video folder name"
                },
                "start": {
                    "type": "number",
                    "description": "Start time in seconds (optional)"
                },
                "end": {
                    "type": "number",
                    "description": "End time in seconds (optional)"
                }
            },
            "required": ["folder"]
        }
    }
}


def handle_request(request):
    """Handle a JSON-RPC request."""
    method = request.get('method', '')
    params = request.get('params', {})
    req_id = request.get('id')

    if method == 'initialize':
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "blindspot",
                    "version": "0.1.0"
                }
            }
        }

    if method == 'notifications/initialized':
        return None  # no response needed

    if method == 'tools/list':
        tools = []
        for name, spec in TOOLS.items():
            tools.append({
                "name": name,
                "description": spec["description"],
                "inputSchema": spec["inputSchema"]
            })
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": tools}
        }

    if method == 'tools/call':
        tool_name = params.get('name', '')
        args = params.get('arguments', {})

        if tool_name == 'blindspot_list_videos':
            result = list_videos()
        elif tool_name == 'blindspot_get_experience':
            result = get_experience(args.get('folder', ''))
        elif tool_name == 'blindspot_get_frame':
            result = get_frame(
                args.get('folder', ''),
                index=args.get('index'),
                timestamp=args.get('timestamp')
            )
        elif tool_name == 'blindspot_get_captions':
            result = get_captions(
                args.get('folder', ''),
                start=args.get('start'),
                end=args.get('end')
            )
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {"type": "text", "text": json.dumps(result, indent=2)}
                ]
            }
        }

    # Unknown method
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"}
    }


def main():
    """Run as stdio MCP server."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + '\n')
            sys.stdout.flush()


if __name__ == '__main__':
    main()
