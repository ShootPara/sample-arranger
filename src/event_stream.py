"""Bounded little-endian ARV1 packets; MIDI stays in memory, never in audio spools."""
from fractions import Fraction
import struct
import threading
from music import validate,TPQ,PARTS


class EventPackets:
    def __init__(self,part):
        if part not in PARTS:raise ValueError("unknown streaming instrument part")
        self.part=part;self.frame=0;self.events=[]
        self.lock=threading.RLock()

    def add_score(self,score,frames,*,start=None):
        with self.lock:return self._add_score(score,frames,start=start)

    def _add_score(self,score,frames,*,start=None):
        validate(score)
        if not 1<=frames<=122*44100 or len(self.events)>2048:raise ValueError("stream score exceeds bounds")
        def sample(tick):return round(Fraction(tick*60*44100,TPQ)/Fraction(str(score["bpm"])))
        notes=[note for note in score["notes"] if note["part"]==self.part]
        if len(notes)>2048:raise ValueError("stream part exceeds note cap")
        origin=self.frame if start is None else start
        if type(origin) is not int or origin<self.frame:raise ValueError("stream score starts before processing cursor")
        for identifier,note in enumerate(notes,1):
            start=min(frames-1,sample(note["tick"]))
            end=min(frames,max(start+1,sample(note["tick"]+note["length"])))
            self.events.extend(((origin+start,1,note["pitch"],note["velocity"],identifier),
                                (origin+end,0,note["pitch"],0,identifier)))
        self.events.sort(key=lambda event:(event[0],event[1])) # offs precede retriggers

    def encode(self,audio):
        with self.lock:return self._encode(audio)

    def _encode(self,audio):
        if len(audio)%8 or not 1<=len(audio)//8<=512:raise ValueError("packet PCM must contain1 to512 stereo frames")
        frames=len(audio)//8;end=self.frame+frames;split=0
        while split<len(self.events) and self.events[split][0]<end:split+=1
        events=self.events[:split]
        if len(events)>256 or any(event[0]<self.frame for event in events):raise ValueError("stream event packet exceeds bounds")
        result=struct.pack("<III",0x31565241,frames,len(events))
        result+=b"".join(struct.pack("<IIIII",event[0]-self.frame,*event[1:]) for event in events)
        result+=audio
        del self.events[:split];self.frame=end
        return result
