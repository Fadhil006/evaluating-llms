"""Generate the video's original, soft instrumental bed; no third-party music."""

import math
import subprocess
from array import array
from pathlib import Path


destination = Path(__file__).resolve().parents[1] / "assets/music/bed.mp3"
sample_rate = 48_000
seconds = 24
chords = ((174.61, 220.0, 261.63), (196.0, 246.94, 293.66),
          (164.81, 207.65, 261.63), (174.61, 220.0, 261.63))
command = ["ffmpeg", "-loglevel", "error", "-y", "-f", "s16le", "-ar", str(sample_rate),
           "-ac", "1", "-i", "pipe:0", "-c:a", "libmp3lame", "-b:a", "96k", str(destination)]
with subprocess.Popen(command, stdin=subprocess.PIPE) as process:
    assert process.stdin is not None
    for start in range(0, seconds * sample_rate, sample_rate):
        block = array("h")
        for i in range(sample_rate):
            t = (start + i) / sample_rate
            chord = chords[min(int(t // 6), 3)]
            fade = min(1.0, t / 0.8, (seconds - t) / 1.2)
            pulse = 0.84 + 0.16 * math.cos(2 * math.pi * t / 2)
            tone = sum(math.sin(2 * math.pi * frequency * t) for frequency in chord) / 3
            block.append(int(32767 * 0.10 * fade * pulse * tone))
        process.stdin.write(block.tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("Could not encode original instrumental bed")
