"""
Blindspot — Video Experience Bridge
Vyre Studio | April 2026

Takes a YouTube URL or local video file and produces a structured
experience document: timestamped captions + frame grabs + scene analysis.
So someone who can't watch can still experience the video.

Phase 1: Core pipeline (CLI)
- yt-dlp for download + caption extraction
- FFmpeg for frame grabs at caption timestamps
- HTML output stitching everything together
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# yt-dlp resolution — may not be on PATH on Windows
# ---------------------------------------------------------------------------
YTDLP = None

def _resolve_ytdlp():
    """Find a working yt-dlp invocation. Cached in module-level YTDLP."""
    global YTDLP
    if YTDLP is not None:
        return YTDLP

    # Try bare command first
    try:
        subprocess.run(
            ['yt-dlp', '--version'],
            capture_output=True, check=True, timeout=10
        )
        YTDLP = ['yt-dlp']
        return YTDLP
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    # Fallback: python -m yt_dlp
    try:
        subprocess.run(
            [sys.executable, '-m', 'yt_dlp', '--version'],
            capture_output=True, check=True, timeout=10
        )
        YTDLP = [sys.executable, '-m', 'yt_dlp']
        return YTDLP
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    YTDLP = []  # empty = not found
    return YTDLP


# ---------------------------------------------------------------------------
# Step labels for progress reporting
# ---------------------------------------------------------------------------
STEP_DOWNLOAD  = '[1/4] Downloading video'
STEP_CAPTIONS  = '[2/4] Extracting captions'
STEP_FRAMES    = '[3/4] Grabbing frames'
STEP_BUILD     = '[4/4] Building experience'

# For local-file mode we adjust numbering (no download)
STEP_LOCAL_CAPTIONS = '[1/3] Checking captions'
STEP_LOCAL_FRAMES   = '[2/3] Grabbing frames'
STEP_LOCAL_BUILD    = '[3/3] Building experience'


def step(label, detail=''):
    """Print a progress step."""
    msg = f'[blindspot] {label}'
    if detail:
        msg += f' — {detail}'
    print(msg)


# ---------------------------------------------------------------------------
# VTT parsing
# ---------------------------------------------------------------------------

def vtt_to_seconds(timestamp):
    """Convert VTT timestamp (HH:MM:SS.mmm) to seconds."""
    parts = timestamp.split(':')
    h, m = int(parts[0]), int(parts[1])
    s = float(parts[2])
    return h * 3600 + m * 60 + s


def seconds_to_display(seconds):
    """Convert seconds to MM:SS display format."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f'{m}:{s:02d}'


def parse_vtt(vtt_path):
    """Parse WebVTT captions into a list of {start, end, text} dicts.

    Includes two-pass dedup:
      1. Exact (start, text) dedup
      2. Fuzzy consecutive dedup — if two adjacent entries have the
         same text, keep only the first (YouTube VTT loves this)
    """
    try:
        with open(vtt_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as exc:
        print(f'[blindspot]   Warning: Could not read caption file ({exc}). Proceeding without captions.')
        return []

    entries = []
    blocks = re.split(r'\n\n+', content.strip())

    for block in blocks:
        lines = block.strip().split('\n')
        for i, line in enumerate(lines):
            match = re.match(
                r'(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})',
                line
            )
            if match:
                start = match.group(1)
                end = match.group(2)
                text_lines = lines[i + 1:]
                text = ' '.join(t.strip() for t in text_lines if t.strip())
                # Strip HTML tags that YouTube sometimes includes
                text = re.sub(r'<[^>]+>', '', text)
                if text:
                    entries.append({
                        'start': start,
                        'end': end,
                        'text': text,
                        'start_seconds': vtt_to_seconds(start)
                    })
                break

    # Pass 1 — exact dedup on (start, text)
    seen = set()
    deduped = []
    for e in entries:
        key = (e['start'], e['text'])
        if key not in seen:
            seen.add(key)
            deduped.append(e)

    # Pass 2 — fuzzy consecutive dedup: same text with different timestamps
    if len(deduped) > 1:
        fuzzy = [deduped[0]]
        for entry in deduped[1:]:
            if entry['text'] != fuzzy[-1]['text']:
                fuzzy.append(entry)
        deduped = fuzzy

    # Pass 3 — rolling overlap dedup: YouTube's rolling captions where
    # each line is the previous text + new words appended.
    # If the next entry starts with or contains the previous entry's text,
    # drop the shorter (previous) one and keep the longer (complete) one.
    if len(deduped) > 1:
        cleaned = []
        i = 0
        while i < len(deduped):
            # Look ahead: if the next entry contains this one's text, skip this one
            if i + 1 < len(deduped):
                curr_text = deduped[i]['text'].strip().lower()
                next_text = deduped[i + 1]['text'].strip().lower()
                if next_text.startswith(curr_text) and len(next_text) > len(curr_text):
                    # This entry is a prefix of the next — skip it, keep the longer one
                    i += 1
                    continue
            cleaned.append(deduped[i])
            i += 1
        deduped = cleaned

    return deduped


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_video(url, output_dir):
    """Download video and captions via yt-dlp.

    Returns (video_path, caption_path, title, video_dir).
    Raises RuntimeError on fatal failures.
    """
    ytdlp = _resolve_ytdlp()
    if not ytdlp:
        raise RuntimeError(
            'yt-dlp is not installed. Install it with:  pip install yt-dlp'
        )

    # --- Fetch title -------------------------------------------------------
    step(STEP_DOWNLOAD, url)
    try:
        info_cmd = [*ytdlp, '--print', '%(title)s', '--no-download', url]
        result = subprocess.run(
            info_cmd, capture_output=True, text=True, timeout=30
        )
        title = result.stdout.strip() or 'untitled'
    except subprocess.SubprocessError as exc:
        print(f'[blindspot]   Warning: Could not fetch title ({exc}). Using "untitled".')
        title = 'untitled'

    safe_title = re.sub(r'[<>:"/\\|?*#%&{}!@\']', '_', title)[:80]
    video_dir = output_dir / safe_title
    video_dir.mkdir(parents=True, exist_ok=True)

    # --- Download video + captions -----------------------------------------
    dl_cmd = [
        *ytdlp,
        '-f', 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
        '--merge-output-format', 'mp4',
        '--write-sub', '--write-auto-sub',
        '--sub-lang', 'en',
        '--sub-format', 'vtt',
        '--restrict-filenames',
        '-o', str(video_dir / 'video.%(ext)s'),
        url
    ]
    try:
        subprocess.run(dl_cmd, check=True, timeout=600)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f'yt-dlp failed (exit code {exc.returncode}). '
            f'Check the URL is valid and yt-dlp is up to date.'
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError('yt-dlp timed out after 10 minutes.')

    # --- Locate files ------------------------------------------------------
    video_path = None
    caption_path = None

    for f in video_dir.iterdir():
        if f.suffix == '.mp4':
            video_path = f
        elif f.suffix == '.vtt':
            caption_path = f

    if not video_path:
        for f in video_dir.iterdir():
            if f.suffix in ('.mp4', '.mkv', '.webm'):
                video_path = f
                break

    return video_path, caption_path, title, video_dir


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

FRAME_OFFSET = 0.5  # seconds — nudge past exact scene transitions

def extract_frames(video_path, captions, output_dir, interval=10):
    """Extract frames at caption timestamps (or at fixed intervals).

    Returns a list of {file, seconds, display} dicts.
    Individual frame failures are skipped gracefully.
    """
    frames_dir = output_dir / 'frames'
    frames_dir.mkdir(exist_ok=True)

    timestamps = None  # will be set when caption-driven

    if captions:
        # Smart mode: grab frame at each caption timestamp
        timestamps = []
        seen_seconds = set()
        for entry in captions:
            sec = int(entry['start_seconds'])
            if sec not in seen_seconds:
                seen_seconds.add(sec)
                timestamps.append(entry['start_seconds'])

        # Thin out if too dense — max ~1 frame per 5 seconds
        if len(timestamps) > 1:
            thinned = [timestamps[0]]
            for t in timestamps[1:]:
                if t - thinned[-1] >= 5:
                    thinned.append(t)
            timestamps = thinned

        total = len(timestamps)
        print(f'[blindspot]   Extracting {total} frames at caption timestamps...')
        failed = 0
        for i, ts in enumerate(timestamps):
            frame_path = frames_dir / f'frame_{i:04d}.jpg'
            # Apply offset to avoid catching exact scene cuts
            seek_time = max(0, ts + FRAME_OFFSET)
            cmd = [
                'ffmpeg', '-ss', str(seek_time),
                '-i', str(video_path),
                '-frames:v', '1',
                '-q:v', '2',
                '-y',
                str(frame_path)
            ]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, timeout=30
                )
                if result.returncode != 0 or not frame_path.exists():
                    failed += 1
                    if frame_path.exists():
                        frame_path.unlink()
            except subprocess.SubprocessError:
                failed += 1

            # Progress indicator every 20 frames
            if (i + 1) % 20 == 0 or (i + 1) == total:
                print(f'[blindspot]   ... {i + 1}/{total} frames')

        if failed:
            print(f'[blindspot]   Warning: {failed} frame(s) failed and were skipped.')

    else:
        # Interval mode: one frame every N seconds
        print(f'[blindspot]   No captions — extracting frames every {interval}s...')
        cmd = [
            'ffmpeg', '-i', str(video_path),
            '-vf', f'fps=1/{interval}',
            '-q:v', '2',
            str(frames_dir / 'frame_%04d.jpg')
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=600)
        except subprocess.SubprocessError as exc:
            print(f'[blindspot]   Warning: FFmpeg interval extraction failed ({exc}).')

    # --- Build frame index -------------------------------------------------
    frame_files = sorted(frames_dir.glob('frame_*.jpg'))
    frame_index = []
    for i, fp in enumerate(frame_files):
        ts = timestamps[i] if timestamps and i < len(timestamps) else i * interval
        frame_index.append({
            'file': fp.name,
            'seconds': ts,
            'display': seconds_to_display(ts)
        })

    return frame_index


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

def build_experience_html(title, captions, frames, output_dir, metadata=None):
    """Build the unified experience HTML document."""

    # Merge captions and frames by timestamp
    events = []
    for f in frames:
        events.append({
            'type': 'frame',
            'seconds': f['seconds'],
            'display': f['display'],
            'file': f['file']
        })
    if captions:
        for c in captions:
            events.append({
                'type': 'caption',
                'seconds': c['start_seconds'],
                'display': seconds_to_display(c['start_seconds']),
                'text': c['text']
            })

    events.sort(key=lambda e: e['seconds'])

    # Group nearby events (within 3 seconds) into moments
    moments = []
    current = {'time': 0, 'display': '0:00', 'frame': None, 'captions': []}

    for event in events:
        if event['seconds'] - current['time'] > 3 and (current['frame'] or current['captions']):
            moments.append(current)
            current = {'time': event['seconds'], 'display': event['display'], 'frame': None, 'captions': []}

        current['time'] = event['seconds']
        current['display'] = event['display']

        if event['type'] == 'frame':
            current['frame'] = event['file']
        elif event['type'] == 'caption':
            current['captions'].append(event['text'])

    if current['frame'] or current['captions']:
        moments.append(current)

    # Build metadata line for subtitle
    meta_parts = ['Generated by Blindspot &mdash; Vyre Studio']
    if metadata:
        if metadata.get('duration_display'):
            meta_parts.append(f'~{metadata["duration_display"]} estimated duration')
        meta_parts.append(metadata.get('generated_at', ''))

    # Generate HTML
    html_parts = [f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Blindspot — {title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #0f0f12;
    color: #e0e0e0;
    font-family: 'Segoe UI', system-ui, sans-serif;
    line-height: 1.6;
    padding: 2rem;
    max-width: 900px;
    margin: 0 auto;
  }}
  h1 {{
    color: #c89cff;
    font-size: 1.5rem;
    margin-bottom: 0.5rem;
  }}
  .subtitle {{
    color: #888;
    font-size: 0.85rem;
    margin-bottom: 2rem;
    border-bottom: 1px solid #2a2a35;
    padding-bottom: 1rem;
  }}
  .moment {{
    display: flex;
    gap: 1.5rem;
    margin-bottom: 1.5rem;
    padding: 1rem;
    background: #1a1a24;
    border-radius: 8px;
    border-left: 3px solid #c89cff;
  }}
  .moment-time {{
    color: #c89cff;
    font-weight: 600;
    font-size: 0.85rem;
    min-width: 50px;
    flex-shrink: 0;
  }}
  .moment-frame {{
    flex-shrink: 0;
  }}
  .moment-frame img {{
    width: 280px;
    border-radius: 4px;
    display: block;
  }}
  .moment-text {{
    flex: 1;
  }}
  .moment-caption {{
    font-size: 0.95rem;
    color: #d0d0d0;
    margin-bottom: 0.3rem;
  }}
  .moment-no-frame {{
    padding-left: 0;
  }}
  .stats {{
    color: #666;
    font-size: 0.8rem;
    margin-top: 2rem;
    text-align: center;
  }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="subtitle">{' &middot; '.join(p for p in meta_parts if p)}</div>
"""]

    for moment in moments:
        html_parts.append('<div class="moment">')
        html_parts.append(f'<div class="moment-time">{moment["display"]}</div>')

        if moment['frame']:
            html_parts.append(f'<div class="moment-frame"><img src="frames/{moment["frame"]}" alt="Frame at {moment["display"]}"></div>')

        if moment['captions']:
            html_parts.append('<div class="moment-text">')
            for cap in moment['captions']:
                html_parts.append(f'<div class="moment-caption">{cap}</div>')
            html_parts.append('</div>')

        html_parts.append('</div>')

    html_parts.append(f"""
<div class="stats">
  {len(frames)} frames &middot; {len(captions) if captions else 0} caption entries &middot; {len(moments)} moments
</div>
</body>
</html>""")

    html_path = output_dir / 'experience.html'
    try:
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(html_parts))
    except OSError as exc:
        print(f'[blindspot]   Error writing HTML: {exc}')
        return None

    return html_path


# ---------------------------------------------------------------------------
# JSON builder
# ---------------------------------------------------------------------------

def build_experience_json(title, captions, frames, output_dir, metadata=None):
    """Build a JSON version for MCP/AI consumption.

    Includes rich metadata: source, duration estimate, counts, timestamp.
    """
    data = {
        'title': title,
        'generated_by': 'Blindspot — Vyre Studio',
        'metadata': metadata or {},
        'moments': []
    }

    # Same merge logic as HTML but output as JSON
    events = []
    for f in frames:
        events.append({
            'type': 'frame',
            'seconds': f['seconds'],
            'display': f['display'],
            'file': f['file']
        })
    if captions:
        for c in captions:
            events.append({
                'type': 'caption',
                'seconds': c['start_seconds'],
                'display': seconds_to_display(c['start_seconds']),
                'text': c['text']
            })

    events.sort(key=lambda e: e['seconds'])

    current = {'time': 0, 'display': '0:00', 'frame': None, 'captions': []}
    for event in events:
        if event['seconds'] - current['time'] > 3 and (current['frame'] or current['captions']):
            data['moments'].append(current)
            current = {'time': event['seconds'], 'display': event['display'], 'frame': None, 'captions': []}
        current['time'] = event['seconds']
        current['display'] = event['display']
        if event['type'] == 'frame':
            current['frame'] = f"frames/{event['file']}"
        elif event['type'] == 'caption':
            current['captions'].append(event['text'])

    if current['frame'] or current['captions']:
        data['moments'].append(current)

    json_path = output_dir / 'experience.json'
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except OSError as exc:
        print(f'[blindspot]   Error writing JSON: {exc}')
        return None

    return json_path


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------

def estimate_duration(captions):
    """Estimate video duration from the last caption end timestamp."""
    if not captions:
        return None, None
    last = captions[-1]
    end_seconds = vtt_to_seconds(last['end'])
    return end_seconds, seconds_to_display(end_seconds)


def build_metadata(source, captions, frames, is_url):
    """Assemble the metadata dict for JSON and HTML output."""
    duration_seconds, duration_display = estimate_duration(captions)
    return {
        'source': source,
        'source_type': 'url' if is_url else 'local_file',
        'duration_seconds': duration_seconds,
        'duration_display': duration_display,
        'total_frames': len(frames),
        'total_captions': len(captions) if captions else 0,
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup_video(video_path, video_dir, is_local):
    """Remove the downloaded video file to save space.

    Never deletes a local source file — only downloaded copies.
    """
    if is_local:
        return  # never touch the user's original file

    target = video_dir / 'video.mp4'
    # Also check common merge outputs
    candidates = list(video_dir.glob('video.*'))
    for f in candidates:
        if f.suffix in ('.mp4', '.mkv', '.webm') and f.exists():
            try:
                f.unlink()
                print(f'[blindspot]   Cleaned up: {f.name}')
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Blindspot — Video Experience Bridge. Vyre Studio.',
        epilog='You designed it. I built it.'
    )
    parser.add_argument('input', help='YouTube URL or path to local video file')
    parser.add_argument('-o', '--output', default='E:/Dante/Vyre Studio/blindspot/output',
                        help='Output directory (default: blindspot/output)')
    parser.add_argument('--interval', type=int, default=10,
                        help='Frame interval in seconds for no-caption fallback (default: 10)')
    parser.add_argument('--no-frames', action='store_true',
                        help='Skip frame extraction (captions only)')
    parser.add_argument('--keep-video', action='store_true',
                        help='Keep the downloaded video file (default: delete after frame extraction)')
    parser.add_argument('--subtitle', type=str, default=None,
                        help='Path to external subtitle file (.srt, .vtt, .txt) to use instead of YouTube captions')

    args = parser.parse_args()
    output_base = Path(args.output)
    output_base.mkdir(parents=True, exist_ok=True)

    input_path = args.input

    # --- Determine input type ---------------------------------------------
    is_url = input_path.startswith('http://') or input_path.startswith('https://')
    is_local = not is_url and Path(input_path).exists()

    if not is_url and not is_local:
        print(f'[blindspot] Error: "{input_path}" is not a valid URL or existing file path.')
        sys.exit(1)

    # --- Step 1: Acquire video --------------------------------------------
    video_path = None
    caption_path = None
    title = 'untitled'
    video_dir = None

    if is_url:
        try:
            video_path, caption_path, title, video_dir = download_video(input_path, output_base)
        except RuntimeError as exc:
            print(f'[blindspot] Error: {exc}')
            sys.exit(1)
    else:
        local_path = Path(input_path).resolve()
        title = local_path.stem
        safe_title = re.sub(r'[<>:"/\\|?*#%&{}!@\']', '_', title)[:80]
        video_dir = output_base / safe_title
        video_dir.mkdir(parents=True, exist_ok=True)
        video_path = local_path
        caption_path = None

        step(STEP_LOCAL_CAPTIONS, local_path.name)
        print('[blindspot]   Local file detected.')

    if not video_path or not video_path.exists():
        print('[blindspot] Error: No video file found after download. Check the URL or file path.')
        sys.exit(1)

    # --- Step 2: Parse captions -------------------------------------------
    captions = []
    step(STEP_CAPTIONS if is_url else STEP_LOCAL_CAPTIONS)

    # Check external subtitle file first (--subtitle flag)
    if args.subtitle and Path(args.subtitle).exists():
        sub_path = Path(args.subtitle)
        print(f'[blindspot]   Using external subtitle: {sub_path.name}')
        # Copy to output folder
        import shutil
        dest = video_dir / sub_path.name
        shutil.copy2(str(sub_path), str(dest))
        # Parse it (handle both VTT and SRT)
        if sub_path.suffix.lower() == '.srt':
            # Convert SRT to VTT first
            vtt_dest = video_dir / 'subtitles.vtt'
            with open(str(sub_path), 'r', encoding='utf-8') as f:
                content = f.read()
            content = content.replace(',', '.')
            with open(str(vtt_dest), 'w', encoding='utf-8') as f:
                f.write('WEBVTT\n\n')
                f.write(content)
            captions = parse_vtt(str(vtt_dest))
        else:
            captions = parse_vtt(str(sub_path))
        print(f'[blindspot]   Found {len(captions)} caption entries from subtitle file.')
    elif caption_path and caption_path.exists():
        print(f'[blindspot]   Parsing captions: {caption_path.name}')
        captions = parse_vtt(str(caption_path))
        print(f'[blindspot]   Found {len(captions)} unique caption entries after dedup.')
    elif is_url:
        print('[blindspot]   No captions available from YouTube.')
    else:
        print('[blindspot]   No captions available.')
        print('[blindspot]   Tip: Add subtitles with --subtitle path/to/file.srt')
        print('[blindspot]   Or use the GUI to upload an .srt file alongside your video.')

    # --- Step 3: Extract frames -------------------------------------------
    frames = []
    if args.no_frames:
        print('[blindspot]   Frame extraction skipped (--no-frames).')
    elif not captions and is_local:
        # No captions on local file = no auto frames. Let user do it manually.
        print('[blindspot]   No captions found — skipping auto frame extraction.')
        print('[blindspot]   Use the mini player in the GUI to grab frames manually.')
    else:
        step(STEP_FRAMES if is_url else STEP_LOCAL_FRAMES)
        frames = extract_frames(video_path, captions, video_dir, args.interval)
        print(f'[blindspot]   Extracted {len(frames)} frames total.')

    # --- Step 4: Build experience documents --------------------------------
    step(STEP_BUILD if is_url else STEP_LOCAL_BUILD)

    metadata = build_metadata(input_path, captions, frames, is_url)
    html_path = build_experience_html(title, captions, frames, video_dir, metadata)
    json_path = build_experience_json(title, captions, frames, video_dir, metadata)

    # --- Cleanup ----------------------------------------------------------
    if not args.keep_video:
        cleanup_video(video_path, video_dir, is_local)

    # --- Summary ----------------------------------------------------------
    print()
    print('[blindspot] Done.')
    if html_path:
        print(f'  Experience (HTML): {html_path}')
    if json_path:
        print(f'  Experience (JSON): {json_path}')
    if frames:
        print(f'  Frames:            {video_dir / "frames"} ({len(frames)} files)')
    if captions:
        print(f'  Captions:          {len(captions)} entries')
    if metadata.get('duration_display'):
        print(f'  Est. duration:     ~{metadata["duration_display"]}')
    if not args.keep_video and is_url:
        print(f'  Video:             cleaned up (use --keep-video to retain)')
    print()
    if html_path:
        print(f'  Open {html_path} in a browser to preview.')


if __name__ == '__main__':
    main()
