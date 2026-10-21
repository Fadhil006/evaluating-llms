# Hyperframes Composition Brief: LLM Comparison Lab

## Objective
Render the 24-second `brag` plan into a clear explanatory walkthrough. Local-only output. No live generation, remote publish, or secret values. User did not request narration.

## Output
- Composition directory: `brag-output/composition/` (created with Hyperframes 0.8.181 blank template)
- Render: `brag-output/brag.mp4`; poster `brag-output/brag.jpg`.
- Format: 1920×1080, 24s, MP4 30fps.

## Source material
Real local React/FastAPI app in `/home/fadhil/Projects/llm-comparison-beginner`.
Primary code: `frontend/src/Experiments.tsx`, `frontend/src/ResultsPanel.tsx`, `frontend/src/style.css`, `docs/BEGINNER_COMPARISON.md`.
Use screenshot assets already copied into `composition/assets/ui/`: `questions-live.png`, `live-model-selection.png`, `live-review.png`, `results-fixture.png`. Do not fetch the current live site from within the composition: screenshot provenance is intentionally frozen. The last image is a synthetic fixture report, **not a real model run**; keep explicit disclaimer throughout that scene.

## Copy that must be legible
- “Two models. The same questions.”
- “Choose questions” / “Choose two provider routes” / “Review: 20 initial requests” / “Compare paired answers.”
- “Illustrative fixtures · not real results” throughout results scene.
- “No overall winner from a small sample.”

## Visuals
Polished calm product walkthrough. Background `#f8fafc`, cards white, navy `#0f172a`, caution amber `#fef3c7`, system sans. Show REAL UI screenshots large and centered. Use selective spotlight or gentle position/scale instead of tiny full-page displays, but never falsify screenshot text/numbers. Prefer readable crop over piling on overlays. Use labels next to screenshot in uncluttered reserved space; actual product UI is the centerpiece. Restrained transitions; keep text settled long enough to read, respect reduced-motion sensibility. If results crop includes real-looking numbers, disclaimer must be adjacent and constantly visible.

## Scenes / timing
Read `../brag-plan.md` first. 0–2 hook; 2–7 questions screenshot; 7–12 models screenshot; 12–17 review screenshot; 17–24 fixture results. Make the final five seconds especially legible. Seek-safe deterministic GSAP timing and a paused `window.__timelines["main"]` registered timeline. Use Hyperframes `data-*` timing contract and local assets.

## Audio
`composition/assets/music/bed.mp3` is an **original locally synthesized track** made by `composition/tools/generate_music.py`, because rights to the bundled third-party track could not be verified for redistribution; keep it low-volume. No SFX, voiceover, remote assets, or claimed beat sync; prioritize text readability. No audio-reactive extraction if it compromises clarity or requires new dependencies; note absence in delivery.

## Validation
Run `npx hyperframes check` before render and fix errors; capture one or two snapshot frames, inspect visually; render high-quality locally. Use ffmpeg/ffprobe to validate video duration/dimensions/audio; choose settled poster frame and bake it into frame 0. Write truthful `share-copy.txt`. Never upload or publish.
