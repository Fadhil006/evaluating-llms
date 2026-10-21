# LLM Comparison Lab video

This 24-second `/brag` walkthrough uses the real local application's question, model-selection and review screens without submitting a comparison. The results segment uses a synthetic-fixture screenshot, visibly labeled **ILLUSTRATIVE FIXTURES — NOT REAL RESULTS**. Do not present it as an authenticated live-model run or as measured evidence of model quality.

- `brag.mp4` — finished local video
- `brag.jpg` — poster frame, also baked into frame 0 of the video
- `brag-plan.md` — storyboard and claim/evidence boundaries
- `composition-brief.md` — rendering brief
- `composition/` — editable Hyperframes source and local media assets
- `share-copy.txt` — postable caption

No provider-generation requests, remote video publication, or exposure of API keys were authorized or performed for this video. Screenshots of the live interface contain selection/review controls only. The demo results are explicitly synthetic.

The quiet instrumental music is original and reproducibly generated with Python's standard library in `composition/tools/generate_music.py`. No third-party music or effects were used: the skill's bundled track was excluded because its exact licensing was not verified.

## Re-render locally

From `brag-output/composition/`, run `python3 tools/generate_music.py`, then `npm run check`, then `npx --yes hyperframes@0.8.181 render --quality high --output ../brag.mp4`. For the delivered file, the renderer's very quiet AAC track was raised **18 dB** without touching the video frames: `ffmpeg -i ../brag.mp4 -c:v copy -af volume=18dB -c:a aac -b:a 128k -movflags +faststart ../brag-audio-adjusted.mp4`. Validate that output, then replace `brag.mp4` with it. The poster is frame 0 (`ffmpeg -i ../brag.mp4 -frames:v 1 ../brag.jpg`). Frame 0 already matches the poster; no different title frame is spliced into the video.

Checked: Hyperframes `npm run check` passed (0 errors, 7 structure/style lint warnings); 24.00 seconds of 1920×1080 H.264 at 30 fps with AAC audio, and several extracted frames were visually inspected. The audio is original music only—there is no spoken narration; all key explanations are on-screen.
