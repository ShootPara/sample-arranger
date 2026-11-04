"""Bounded in-memory musical edit history; never retains audio or writes projects."""
import json


def encode(state):return json.dumps(state,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':')).encode('utf-8')


class PlanHistory:
    def __init__(self,max_entries=32,max_bytes=8*1024**2):
        self.past=[];self.future=[];self.max_entries=max_entries;self.max_bytes=max_bytes

    def _append(self,stack,state):
        payload=encode(state)
        if len(payload)>2*1024**2:raise ValueError('plan is too large for bounded edit history')
        stack.append(payload)
        while len(self.past)+len(self.future)>self.max_entries or sum(map(len,self.past+self.future))>self.max_bytes:
            target=self.past if self.past and stack is self.future else self.future if self.future and stack is self.past else stack
            target.pop(0)

    def remember(self,state):
        self.future.clear();self._append(self.past,state)

    def undo(self,current):
        if not self.past:return None
        previous=self.past.pop();self._append(self.future,current);return json.loads(previous)

    def redo(self,current):
        if not self.future:return None
        following=self.future.pop();self._append(self.past,current);return json.loads(following)

    def clear(self):self.past.clear();self.future.clear()
