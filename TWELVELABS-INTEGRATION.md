# Twelvelabs Integration Notes — Blindspot

## API Flow

```
1. create-index (once)
   → name: "blindspot", models: ["generative"]
   → Returns indexId — store in config

2. start-video-indexing-task (per video)
   → videoFilePath: local path to downloaded mp4
   → indexId: from step 1
   → Returns taskId — poll until complete

3. analyse-video (after indexing complete)
   → videoId: from indexed video
   → prompt: "Describe each scene chronologically. Include: 
      timestamp, visual setting, people/objects visible, 
      actions occurring, mood/lighting, any on-screen text. 
      Format as timestamped entries."
   → Returns structured scene descriptions

4. search (optional, for later MCP queries)
   → query: natural language ("when does the person hold up the device")
   → Returns timestamped segments with thumbnails
```

## Integration Point in Pipeline

After yt-dlp downloads the video and before/during frame extraction:

```
download → captions → [upload to Twelvelabs] → frames → [get analysis] → stitch
```

Twelvelabs indexing takes time (async). Two approaches:
- **Blocking:** wait for indexing + analysis before building output. Slower but complete.
- **Two-pass:** build v1 output with captions + frames immediately. Then when Twelvelabs finishes, rebuild with analysis merged in. Better UX.

## MCP Tools Available

| Tool | Purpose |
|------|---------|
| `create-index` | One-time setup |
| `start-video-indexing-task` | Upload + index video (accepts local file path!) |
| `analyse-video` | Generate scene descriptions with prompt |
| `search` | Natural language search across indexed videos |
| `list-videos` | See what's been indexed |
| `list-indexes` | See available indexes |

## Config Needed
- Twelvelabs API key (user provides their own)
- Index ID (created once, stored in blindspot config)
- Currently: API key not configured on our machine. Phase 4 work.

## Analysis Prompt Strategy

The prompt matters — it drives the quality of scene descriptions. Test prompts:

**Comprehensive:**
"Describe each distinct scene in this video chronologically. For each scene include: approximate timestamp, visual setting and environment, people or objects visible, actions occurring, mood and lighting, any on-screen text or graphics. Be specific and visual — the reader cannot see the video."

**Concise:**
"Provide a timestamped scene-by-scene summary. Focus on what is visually happening, not just what is being said. Include setting, actions, and notable visual details."

**For music videos:**
"Describe the visual narrative scene by scene with timestamps. Include: setting changes, choreography, costume changes, color palette shifts, camera movements, and symbolic imagery."
