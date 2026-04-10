"""
Blindspot Backend Server — bridges the GUI to the pipeline.

Runs a local Flask server that the GUI talks to via HTTP.
Handles: processing videos, streaming progress, serving files,
custom frame grabs from the mini player.

Usage:
  python server.py              # starts on port 8765
  python server.py --port 9000  # custom port
"""

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory, Response, send_file

app = Flask(__name__)

OUTPUT_DIR = Path('E:/Dante/Vyre Studio/blindspot/output')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Global progress queue — SSE consumers read from here
progress_queues = []
current_job = {'active': False, 'folder': None}


def broadcast_progress(step, detail='', pct=0):
    """Send progress update to all SSE listeners."""
    msg = json.dumps({'step': step, 'detail': detail, 'pct': pct})
    dead = []
    for q in progress_queues:
        try:
            q.put_nowait(msg)
        except Exception:
            dead.append(q)
    for q in dead:
        progress_queues.remove(q)


def run_pipeline(input_path, keep_video=False):
    """Run the Blindspot pipeline in a background thread."""
    current_job['active'] = True
    current_job['folder'] = None

    try:
        # Build command
        cmd = [
            sys.executable,
            str(Path(__file__).parent / 'blindspot.py'),
            input_path,
            '-o', str(OUTPUT_DIR)
        ]
        if keep_video:
            cmd.append('--keep-video')

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        for line in process.stdout:
            line = line.strip()
            if not line:
                continue

            # Skip yt-dlp warnings entirely
            if line.startswith('WARNING') or 'WARNING' in line:
                broadcast_progress('info', f'(skipped warning)', -1)
                continue

            # Parse progress from pipeline output
            if '[1/4]' in line or '[1/3]' in line:
                broadcast_progress('download', line, 10)
            elif '[2/4]' in line or '[2/3]' in line:
                broadcast_progress('captions', line, 35)
            elif '[3/4]' in line:
                broadcast_progress('frames', line, 60)
            elif '[3/3]' in line:
                broadcast_progress('frames', line, 60)
            elif '[4/4]' in line:
                broadcast_progress('build', line, 85)
            elif 'Done.' in line:
                broadcast_progress('done', 'Processing complete!', 100)
            elif 'Experience (HTML):' in line:
                # Extract folder name from path
                match = re.search(r'output[/\\](.+?)[/\\]experience\.html', line)
                if match:
                    current_job['folder'] = match.group(1)
            elif '...' in line and 'frames' in line.lower():
                broadcast_progress('frames', line, 65)
            elif ('Error' in line or 'error' in line) and 'WARNING' not in line and 'warning' not in line and 'encounter error' not in line.lower():
                broadcast_progress('error', line, 0)
            else:
                broadcast_progress('info', line, -1)

        process.wait()

        if process.returncode != 0:
            broadcast_progress('error', f'Pipeline exited with code {process.returncode}', 0)
        elif not current_job['folder']:
            # Try to find the folder from output dir
            folders = sorted(OUTPUT_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            for f in folders:
                if f.is_dir() and (f / 'experience.json').exists():
                    current_job['folder'] = f.name
                    break

    except Exception as e:
        broadcast_progress('error', str(e), 0)
    finally:
        current_job['active'] = False


# ── API Routes ─────────────────────────────────────────────────────

@app.route('/')
def index():
    """Serve the GUI."""
    gui_dir = Path(__file__).parent / 'gui'
    return send_from_directory(str(gui_dir), 'index.html')


@app.route('/gui/<path:filename>')
def gui_static(filename):
    """Serve GUI static files (font, etc)."""
    gui_dir = Path(__file__).parent / 'gui'
    return send_from_directory(str(gui_dir), filename)


@app.route('/api/process', methods=['POST'])
def process_video():
    """Start processing a video URL or file path."""
    if current_job['active']:
        return jsonify({'error': 'A job is already running'}), 409

    data = request.json or {}
    input_path = data.get('input', '').strip()
    keep_video = data.get('keep_video', False)  # YouTube embed handles playback, no need to keep

    if not input_path:
        return jsonify({'error': 'No input provided'}), 400

    # Validate
    is_url = input_path.startswith('http://') or input_path.startswith('https://')
    is_file = not is_url and Path(input_path).exists()

    if not is_url and not is_file:
        return jsonify({'error': f'Not a valid URL or file path: {input_path}'}), 400

    # Start pipeline in background
    thread = threading.Thread(
        target=run_pipeline,
        args=(input_path, keep_video),
        daemon=True
    )
    thread.start()

    return jsonify({'status': 'started', 'input': input_path})


@app.route('/api/progress')
def progress_stream():
    """SSE endpoint — stream progress updates to the GUI."""
    q = queue.Queue()
    progress_queues.append(q)

    def generate():
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield f'data: {msg}\n\n'
                except queue.Empty:
                    yield f'data: {json.dumps({"step": "heartbeat"})}\n\n'
        except GeneratorExit:
            if q in progress_queues:
                progress_queues.remove(q)

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/status')
def job_status():
    """Get current job status."""
    return jsonify({
        'active': current_job['active'],
        'folder': current_job['folder']
    })


@app.route('/api/videos')
def list_videos():
    """List all processed videos."""
    videos = []
    if OUTPUT_DIR.exists():
        for d in sorted(OUTPUT_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if d.is_dir() and (d / 'experience.json').exists():
                try:
                    with open(d / 'experience.json', 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    meta = data.get('metadata', {})
                    videos.append({
                        'title': data.get('title', d.name),
                        'folder': d.name,
                        'moments': len(data.get('moments', [])),
                        'duration': meta.get('duration_display', ''),
                        'total_frames': meta.get('total_frames', 0),
                        'generated_at': meta.get('generated_at', '')
                    })
                except Exception:
                    videos.append({'title': d.name, 'folder': d.name, 'error': True})

    return jsonify({'videos': videos, 'count': len(videos)})


@app.route('/api/experience/<path:folder>')
def get_experience(folder):
    """Get the experience JSON for a video."""
    json_file = OUTPUT_DIR / folder / 'experience.json'
    if not json_file.exists():
        return jsonify({'error': 'Not found'}), 404
    return send_file(str(json_file), mimetype='application/json')


@app.route('/api/video/<path:folder>')
def serve_video(folder):
    """Serve the video file for the mini player."""
    video_dir = OUTPUT_DIR / folder
    for ext in ('.mp4', '.mkv', '.webm'):
        video_file = video_dir / f'video{ext}'
        if video_file.exists():
            return send_file(str(video_file))
    return jsonify({'error': 'No video file found. Was --keep-video used?'}), 404


@app.route('/api/frames/<path:folder>/<filename>')
def serve_frame(folder, filename):
    """Serve a frame image."""
    frame_path = OUTPUT_DIR / folder / 'frames' / filename
    if not frame_path.exists():
        return jsonify({'error': 'Frame not found'}), 404
    return send_file(str(frame_path))


@app.route('/api/grab', methods=['POST'])
def grab_custom_frame():
    """Grab a frame at a specific timestamp from a video.

    The human scrubs the mini player, clicks grab — this extracts
    the frame server-side and saves it as a custom annotation.
    """
    data = request.json or {}
    folder = data.get('folder', '')
    timestamp = data.get('timestamp', 0)
    note = data.get('note', '')

    video_dir = OUTPUT_DIR / folder
    if not video_dir.exists():
        return jsonify({'error': 'Video folder not found'}), 404

    # Find the video file — check local first, then try source URL
    video_path = None
    for ext in ('.mp4', '.mkv', '.webm'):
        vp = video_dir / f'video{ext}'
        if vp.exists():
            video_path = vp
            break

    # If no local video, check if we have the source URL to grab from
    source_url = None
    if not video_path:
        exp_file = video_dir / 'experience.json'
        if exp_file.exists():
            try:
                with open(exp_file, 'r', encoding='utf-8') as f:
                    exp = json.load(f)
                source_url = (exp.get('metadata', {}) or {}).get('source', '')
                if not source_url.startswith('http'):
                    source_url = None
            except Exception:
                pass

    if not video_path and not source_url:
        return jsonify({'error': 'No video file or source URL available for frame grab.'}), 404

    # If we only have URL, download a tiny segment around the timestamp
    temp_video = None
    if not video_path and source_url:
        try:
            import tempfile
            temp_dir = Path(tempfile.mkdtemp())
            temp_video = temp_dir / 'temp_grab.mp4'
            # Use yt-dlp + ffmpeg to grab just a few seconds around the timestamp
            ytdlp = [sys.executable, '-m', 'yt_dlp']
            stream_cmd = [*ytdlp, '-f', 'best[height<=720]', '-g', source_url]
            result = subprocess.run(stream_cmd, capture_output=True, text=True, timeout=15)
            stream_url = result.stdout.strip().split('\n')[0]
            if stream_url:
                # Grab a short segment using ffmpeg with the stream URL
                subprocess.run([
                    'ffmpeg', '-ss', str(max(0, timestamp - 1)),
                    '-i', stream_url,
                    '-t', '3',
                    '-c', 'copy',
                    '-y', str(temp_video)
                ], capture_output=True, timeout=30)
                if temp_video.exists():
                    video_path = temp_video
        except Exception:
            pass

    if not video_path:
        return jsonify({'error': 'Could not access video for frame grab.'}), 404

    # Extract frame at timestamp
    custom_dir = video_dir / 'custom_frames'
    custom_dir.mkdir(exist_ok=True)

    frame_name = f'custom_{int(timestamp * 100):08d}.jpg'
    frame_path = custom_dir / frame_name

    try:
        subprocess.run([
            'ffmpeg', '-ss', str(timestamp),
            '-i', str(video_path),
            '-frames:v', '1',
            '-q:v', '2',
            '-y',
            str(frame_path)
        ], capture_output=True, timeout=15, check=True)
    except Exception as e:
        return jsonify({'error': f'Frame extraction failed: {e}'}), 500

    # Clean up temp video if we downloaded one
    if temp_video and temp_video.exists():
        try:
            temp_video.unlink()
            temp_video.parent.rmdir()
        except Exception:
            pass

    if not frame_path.exists():
        return jsonify({'error': 'Frame file not created'}), 500

    # Save to custom grabs manifest
    manifest_path = video_dir / 'custom_grabs.json'
    grabs = []
    if manifest_path.exists():
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                grabs = json.load(f)
        except Exception:
            grabs = []

    m = int(timestamp) // 60
    s = int(timestamp) % 60
    display = f'{m}:{s:02d}'

    grabs.append({
        'timestamp': timestamp,
        'display': display,
        'note': note,
        'frame': f'custom_frames/{frame_name}',
        'grabbed_at': datetime.now(timezone.utc).isoformat(),
        'source': 'human'
    })

    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(grabs, f, indent=2)

    return jsonify({
        'success': True,
        'frame': f'custom_frames/{frame_name}',
        'display': display,
        'note': note,
        'frame_url': f'/api/custom_frame/{folder}/{frame_name}'
    })


@app.route('/api/custom_frame/<path:folder>/<filename>')
def serve_custom_frame(folder, filename):
    """Serve a custom-grabbed frame."""
    frame_path = OUTPUT_DIR / folder / 'custom_frames' / filename
    if not frame_path.exists():
        return jsonify({'error': 'Custom frame not found'}), 404
    return send_file(str(frame_path))


@app.route('/api/custom_grabs/<path:folder>')
def list_custom_grabs(folder):
    """List all custom frame grabs for a video."""
    manifest_path = OUTPUT_DIR / folder / 'custom_grabs.json'
    if not manifest_path.exists():
        return jsonify({'grabs': [], 'count': 0})
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            grabs = json.load(f)
        return jsonify({'grabs': grabs, 'count': len(grabs)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── CORS ───────────────────────────────────────────────────────────

@app.after_request
def add_cors(response):
    """Allow the GUI to talk to us from file:// or localhost."""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response


# ── Entry ──────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Blindspot Backend Server')
    parser.add_argument('--port', type=int, default=8765, help='Port (default: 8765)')
    args = parser.parse_args()

    print(f'[blindspot-server] Starting on http://localhost:{args.port}')
    print(f'[blindspot-server] Output dir: {OUTPUT_DIR}')
    print(f'[blindspot-server] GUI: http://localhost:{args.port}/')

    app.run(host='127.0.0.1', port=args.port, debug=False, threaded=True)
