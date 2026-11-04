"""Estimate rhythmic periodicity from an audio onset envelope."""
import argparse
import json
import math
import subprocess
from process import run
from array import array
from pathlib import Path


def measure(path: Path) -> dict:
    decoded = run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path.resolve()),
         "-t", "30", "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
        check=True, capture_output=True, timeout=45,
    )
    pcm = array("h", decoded.stdout)
    levels = [
        math.log1p(sum(abs(value) for value in pcm[i:i + 80]) / 80)
        for i in range(0, len(pcm) - 79, 80)
    ]
    onsets = [max(0.0, right - left) for left, right in zip(levels, levels[1:])]
    result = {"bpm": None, "confidence": 0.0, "source": "audio_onset_autocorrelation",
              "analyzed_seconds": len(pcm) / 8000}
    if len(onsets) < 250 or max(onsets) < 0.1:
        return result
    mean = sum(onsets) / len(onsets)
    centered = [value - mean for value in onsets]
    scores = {}
    for lag in range(29, 102):
        left, right = centered[:-lag], centered[lag:]
        norm = math.sqrt(sum(x*x for x in left) * sum(x*x for x in right))
        scores[lag] = sum(a*b for a, b in zip(left, right)) / norm if norm else 0
    peaks = [lag for lag in range(30, 101)
             if scores[lag] > scores[lag - 1] and scores[lag] >= scores[lag + 1]]
    if not peaks:
        return result
    lag = max(peaks, key=scores.get)
    score = scores[lag]
    if score < 0.3:
        return result
    rivals = [scores[other] for other in peaks if abs(other - lag) > 3]
    confidence = score * (1 - max(0, max(rivals, default=0)))
    offset = 0.5 * (scores[lag - 1] - scores[lag + 1]) / (
        scores[lag - 1] - 2 * score + scores[lag + 1]
    )
    result.update(bpm=round(6000 / (lag + offset), 2),
                  confidence=round(confidence, 3))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(measure(args.audio)))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"tempo analysis failed: {error}\n")
