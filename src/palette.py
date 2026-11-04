"""App-authored additive instruments; no downloaded recordings/styles/presets.

The synthesis algorithms are app code. Generated audio carries no extra asset
license restriction from this palette. User samples/plugins keep their own terms.
"""
from fractions import Fraction
from pathlib import Path
import wave
from music import TPQ,validate


def render_score(score,path,*,frames_override=None,fade_end=True):
    import numpy as np
    validate(score)
    tempo=Fraction(str(score["bpm"]))
    frames=score.get("duration_frames",round(Fraction(score["duration_ticks"]*60*44100,TPQ)/tempo))
    if frames_override is not None:
        if type(frames_override) is not int or abs(frames_override-frames)>1:
            raise ValueError("sample-clock adjustment must be at most one frame")
        frames=frames_override
    if frames*4+44>43_000_000:raise ValueError("palette render exceeds byte cap")
    notes=[]
    for note in score["notes"]:
        start=round(Fraction(note["tick"]*60*44100,TPQ)/tempo)
        end=round(Fraction((note["tick"]+note["length"])*60*44100,TPQ)/tempo)
        notes.append((start,end,note))
    with wave.open(str(path),"wb") as output:
        output.setparams((2,2,44100,0,"NONE","not compressed"))
        for start in range(0,frames,4096):
            positions=np.arange(start,min(start+4096,frames))
            audio=np.zeros((len(positions),2),dtype=np.float64)
            for begin,end,note in notes:
                if end<=start or begin>=start+len(positions):continue
                mask=(positions>=begin)&(positions<end)
                time=(positions[mask]-begin)/44100
                remaining=(end-positions[mask])/44100
                envelope=np.minimum(1,time/0.012)*np.minimum(1,remaining/0.08)
                frequency=440*2**((note["pitch"]-69)/12)
                phase=2*np.pi*frequency*time
                if note["part"]=="bass":
                    signal=np.sin(phase)+0.2*np.sin(2*phase)
                    envelope*=np.exp(-0.7*time);pan=0.5;gain=0.16
                elif note["part"]=="chords":
                    signal=np.sin(phase)+0.12*np.sin(3*phase)
                    envelope*=np.exp(-0.35*time);pan=0.35;gain=0.055
                else:
                    signal=np.sin(phase)+0.2*np.sin(2*phase)*np.exp(-4*time)
                    envelope*=np.exp(-2.5*time);pan=0.65;gain=0.12
                signal*=envelope*gain*note["velocity"]/100
                audio[mask,0]+=signal*(1-pan)**0.5
                audio[mask,1]+=signal*pan**0.5
            # A bounded final release prevents clicks when the duration is a hard constraint.
            if fade_end:audio*=np.minimum(1,(frames-positions)/3528)[:,None]
            output.writeframesraw((np.tanh(audio)*30000).astype("<i2").tobytes())
    return {"frames":frames,"palette":"additive-1","rights":"app-authored synthesis; no third-party recordings"}
