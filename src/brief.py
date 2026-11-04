"""Deterministic brief interpretation with explicit refinement precedence."""
import re
from planner import local_sections


def interpret(initial, refined=None):
    text = refined if refined is not None else initial
    if not isinstance(text,str) or len(text.encode("utf-8"))>12000:raise ValueError("brief must be bounded text")
    normalized=re.sub(r"\b(one|two|three|four)\b",lambda match:str({"one":1,"two":2,"three":3,"four":4}[match[0].lower()]),text,flags=re.I)
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*(minutes?|mins?|seconds?|secs?)\b", normalized, re.I)
    durations = {float(value) * (60 if unit.lower().startswith("m") else 1)
                 for value, unit in matches}
    result = {"initial": initial, "effective": text, "refined": refined is not None}
    issues=[]
    if len(durations)!=1:issues.append("Specify one duration in seconds or minutes, up to four minutes.")
    seconds=next(iter(durations)) if len(durations)==1 else None
    if seconds is not None and not 0.1<=seconds<=240:issues.append("Duration must be between0.1 and240 seconds.")
    tempi={float(value) for value in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)\s*bpm\b",text,re.I)}
    if len(tempi)>1 or any(not 40<=bpm<=240 for bpm in tempi):issues.append("Specify one tempo from40 to240 BPM.")
    keys={(pitch.upper().replace("♯","#").replace("♭","b"),mode.lower())
          for pitch,mode in re.findall(r"\b([A-G](?:#|b|♯|♭)?)\s+(major|minor)\b",text,re.I)}
    if len(keys)>1:issues.append("Specify one major or minor key.")
    if issues:
        result.update(state="needs_input" if refined is None else "invalid",message=" ".join(issues))
        return result
    excluded=set(re.findall(r"\b(?:no|without|exclude)\s+(drums?|bass|piano|guitar|pads?)\b",text.lower()))
    excluded={role.rstrip("s") if role in ("drums","pads") else role for role in excluded}
    roles = [role for role in ("drum", "bass", "piano", "guitar", "pad")
             if re.search(r"\b"+role+r"s?\b",text,re.I) and role not in excluded]
    bpm = next(iter(tempi)) if tempi else 128 if any(word in text.lower() for word in ("upbeat", "energetic")) else None
    musical={"density":"sparse" if re.search(r"\b(sparse|minimal|calm)\b",text,re.I) else "busy" if re.search(r"\b(busy|dense)\b",text,re.I) else "medium"}
    if keys:
        pitch,mode=next(iter(keys));base={"C":0,"D":2,"E":4,"F":5,"G":7,"A":9,"B":11}[pitch[0]]
        musical.update(root=(base+(1 if pitch.endswith('#') else -1 if pitch.endswith(('B','b')) and len(pitch)>1 else 0))%12,mode=mode)
    if "bass" in excluded:musical["parts"]=["chords","melody"]
    if re.search(r'\b(bed|narration|voiceover|underscore)\b',text,re.I):musical['form']='bed'
    result.update(state="ready", seconds=seconds, role=roles[0] if roles else "",
                  recommended_bpm=bpm,musical=musical,excluded_roles=sorted(excluded))
    return result


def plan(database, initial, refined=None):
    intent = interpret(initial, refined)
    if intent["state"] == "ready":
        intent["sections"] = local_sections(database, intent["role"], intent["seconds"],
                                           intent["recommended_bpm"],excluded_roles=intent["excluded_roles"])
    return intent


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("initial")
    parser.add_argument("--refined")
    args = parser.parse_args()
    try:
        print(json.dumps(plan(args.catalog, args.initial, args.refined)))
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")
