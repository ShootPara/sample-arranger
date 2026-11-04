"""Opt-in local stderr stage events. No persistence, telemetry or private content."""
import json
import os
import sys


def emit(kind,**fields):
    if os.environ.get('ARRANGER_EVENT_STREAM')=='1':
        print(json.dumps({'event':{'schema':1,'kind':kind,**fields}},allow_nan=False),file=sys.stderr,flush=True)
