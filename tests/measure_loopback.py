"""Opt-in, synthetic-only process WASAPI diagnostic; not a microphone recording.

Run manually with Python/Numpy. Captured PCM is deleted on exit. Reports Windows
audio-engine evidence, not acoustic speaker/physical cable-loopback evidence.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import numpy as np
import argparse
import sys
import threading
import wave
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from device import DeviceStream


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline",action="store_true",help="measure the real chunk adapter plus persistent delay effect")
    parser.add_argument('--ensemble',action='store_true',help='add three persistent muted instruments with known aggregate latency')
    args=parser.parse_args()
    build = Path(os.environ["LOCALAPPDATA"], "SampleArranger/tools/arranger-native")
    frames = 44100 * 8
    t = np.arange(frames) / 44100
    mono = (0.12 * np.sin(2 * np.pi * 997 * t)).astype("float32")
    signal = np.repeat(mono[:, None], 2, axis=1)
    with tempfile.TemporaryDirectory(prefix="arranger-synthetic-loopback-") as folder:
        path = Path(folder) / "capture.f32"
        instruments=None
        if args.ensemble:
            from plugins import capture_state
            saved=capture_state(build/'arranger-vst3.exe',build/'arranger-delay-fixture.vst3',
                '6623100314424231A562100212142801',Path(folder)/'presets',parameters={'1':0})
            instruments={part:{'plugin':str(build/'arranger-delay-fixture.vst3'),'class_id':saved['class_id'],'state':saved['state']} for part in ('bass','chords','melody')}
        device=DeviceStream(build/"arranger-playback.exe",build/"arranger-vst3.exe",build/"arranger-delay-fixture.vst3",bpm=137,instruments=instruments) if args.pipeline or args.ensemble else None
        player=device.player if device else subprocess.Popen([str(build / "arranger-playback.exe")], stdin=subprocess.PIPE,
                                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        probe = subprocess.Popen([str(build / "arranger-loopback-probe.exe"), str(player.pid), "11", str(path)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            ready = probe.stdout.readline().strip()
            if ready != "ready":
                raise RuntimeError(f"Process-loopback unavailable: {ready} {probe.communicate(timeout=12)}")
            time.sleep(0.5)
            # Prime the newly opened render endpoint with silence before the measured signal.
            if device:
                stop=threading.Event()
                chunks=[np.zeros((22050,2),dtype="float32"),*np.split(signal,8),np.zeros((22050,2),dtype="float32")]
                for index,chunk in enumerate(chunks):
                    source=Path(folder)/f"synthetic-{index}.wav"
                    with wave.open(str(source),"wb") as output:
                        output.setparams((2,2,44100,0,"NONE","not compressed"))
                        output.writeframes((chunk*32767).astype("<i2").tobytes())
                    if instruments:
                        from music import compile_intent
                        device.consume(source,stop,score=compile_intent({'seconds':len(chunk)/44100,'bpm':137}))
                    else:device.consume(source,stop)
                    source.unlink()
                device.drain()
            else:
                player.stdin.write(bytes(22050 * 8));player.stdin.flush()
                for chunk in np.split(signal,8):player.stdin.write(chunk.tobytes());player.stdin.flush()
                player.stdin.close();player.wait(timeout=15)
            stdout, stderr = probe.communicate(timeout=15)
            if player.returncode or probe.returncode:
                raise RuntimeError(f"player={player.returncode}; probe={probe.returncode}: {stderr}")
            captured = np.fromfile(path, dtype="float32").reshape(-1, 2)[:, 0]
            # A 1 ms RMS window catches audible zero gaps without mistaking sine crossings for silence.
            window = 44
            rms = np.sqrt(np.convolve(captured.astype(float) ** 2, np.ones(window) / window, mode="valid"))
            active = np.flatnonzero(rms > 0.01)
            if not len(active):
                raise AssertionError("loopback is silent")
            interior = rms[active[0] + 441:active[-1] - 441]
            start = int(active[0]) + 4410
            known = captured[start:start + 7 * 44100].astype(float)
            phase = np.arange(len(known)) * (2 * np.pi * 997 / 44100)
            basis = np.column_stack((np.sin(phase), np.cos(phase)))
            fit = basis @ np.linalg.lstsq(basis, known, rcond=None)[0]
            residual_ratio = float(np.sqrt(np.mean((known - fit) ** 2)) / np.sqrt(np.mean(known ** 2)))
            result = {"capture": "WASAPI process-tree loopback, synthetic player only",
                      "physical_acoustic_capture": False,
                      "pipeline": "DeviceStream + three persistent muted instruments + controlled effect" if instruments else "DeviceStream + persistent controlled effect" if device else "native sink directly",
                      'instrument_latency_samples':device.ensemble.latency if instruments else None,
                      "logical_chunks": 8, "source_frames": frames,
                      "captured_frames": len(captured),
                      "active_seconds": len(active) / 44100,
                      "minimum_interior_1ms_rms": float(interior.min()),
                      "interior_silent_windows": int(np.sum(interior < 0.005)),
                      "sinusoid_residual_rms_ratio": residual_ratio,
                      "probe": stdout.strip()}
            print(json.dumps(result, indent=2))
            assert result["interior_silent_windows"] == 0, "gap detected inside synthetic signal"
            assert abs(result["active_seconds"] - 8) < 0.03, "missing/repeated duration"
            assert residual_ratio < 0.01, "phase discontinuity or unexpected signal distortion"
        finally:
            if device:device.close()
            for process in (player, probe):
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
