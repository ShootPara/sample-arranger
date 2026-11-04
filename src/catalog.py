"""Local, read-only sample discovery and SQLite catalog."""
import argparse
import json
import re
import sqlite3
import subprocess
import wave
from datetime import datetime,timezone
from contextlib import closing
from pathlib import Path
from tempo import measure

AUDIO = {".wav", ".flac", ".mp3", ".ogg", ".aiff", ".aif"}
BPM_HINT = re.compile(r"(?<![\d.])(\d{2,3}(?:\.\d+)?)\s*bpm\b", re.I)


def correction_record(db,path,size,modified_ns):
    columns={row[1] for row in db.execute('PRAGMA table_info(tempo_correction)')}
    if not columns:return None
    fields=['bpm']+(['bytes','modified_ns','corrected_utc'] if 'corrected_utc' in columns else [])
    row=db.execute('SELECT '+','.join(fields)+' FROM tempo_correction WHERE path=?',(path,)).fetchone()
    if row is None:return None
    result=dict(zip(fields,row))
    result.update(source='user_correction',valid=(result.get('bytes'),result.get('modified_ns'))==(size,modified_ns),
                  identity='stat fingerprint; not content hash')
    if not result['valid']:result['status']='review_required_changed_or_legacy_source'
    return result


def describe_sample(row, db):
    result = dict(row)
    hints = {float(value) for value in BPM_HINT.findall(Path(result["name"]).stem)}
    bpm = next(iter(hints)) if len(hints) == 1 else None
    result["bpm_hint"] = bpm if bpm is not None and 20 <= bpm <= 400 else None
    result["bpm_source"] = "filename" if result["bpm_hint"] is not None else None
    record = db.execute(
        """SELECT bpm, confidence, source, analyzed_seconds FROM tempo_measurement
        WHERE path = ? AND modified_ns = ? AND bytes = ?""",
        (row["path"], row["modified_ns"], row["bytes"]),
    ).fetchone()
    correction=correction_record(db,row['path'],row['bytes'],row['modified_ns'])
    result["tempo_measurement"] = dict(record) if record else None
    result["tempo_correction"] = correction["bpm"] if correction and correction['valid'] else None
    result['tempo_correction_record']=correction
    metadata=db.execute('SELECT payload,inspected_utc FROM metadata_observation WHERE path=? AND bytes=? AND modified_ns=?',
                        (row['path'],row['bytes'],row['modified_ns'])).fetchone()
    result['embedded_metadata']={**json.loads(metadata[0]),'inspected_utc':metadata[1]} if metadata else None
    from catalog_identity import observed,annotation
    result['content_identity']=observed(db,row)
    result['musical_annotation']=annotation(db,row)
    return result

def main():
    from process_group import own_process_tree
    own_process_tree()
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    commands = parser.add_subparsers(dest="operation", required=True)
    scan = commands.add_parser("scan")
    scan.add_argument("root", type=Path)
    scan.add_argument("--metadata-only", action="store_true", help="Skip opening audio files")
    query = commands.add_parser("search")
    query.add_argument("term", nargs="?", default="")
    query.add_argument("--limit", type=int, choices=range(1, 101), default=20)
    query.add_argument("--offset",type=int,default=0)
    commands.add_parser("measure").add_argument("path", type=Path)
    commands.add_parser("metadata").add_argument("path",type=Path)
    correction = commands.add_parser("correct-tempo")
    correction.add_argument("path", type=Path)
    correction.add_argument("bpm", type=float)
    args = parser.parse_args()
    if args.operation == "scan" and not (args.root.is_dir() or args.root.is_file()):
        parser.error("sample root must be an accessible directory or file")
    with closing(sqlite3.connect(args.db)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("""CREATE TABLE IF NOT EXISTS sample (
            path TEXT PRIMARY KEY, name TEXT NOT NULL, bytes INTEGER NOT NULL,
            modified_ns INTEGER NOT NULL, seconds REAL, duration_source TEXT
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS tempo_measurement (
            path TEXT PRIMARY KEY, modified_ns INTEGER NOT NULL, bytes INTEGER NOT NULL,
            bpm REAL, confidence REAL NOT NULL, source TEXT NOT NULL, analyzed_seconds REAL NOT NULL
        )""")
        db.execute("CREATE TABLE IF NOT EXISTS tempo_correction (path TEXT PRIMARY KEY, bpm REAL NOT NULL)")
        columns={row[1] for row in db.execute('PRAGMA table_info(tempo_correction)')}
        for name,kind in (('bytes','INTEGER'),('modified_ns','INTEGER'),('corrected_utc','TEXT')):
            if name not in columns:db.execute(f'ALTER TABLE tempo_correction ADD COLUMN {name} {kind}')
        db.execute('CREATE TABLE IF NOT EXISTS tempo_correction_history (path TEXT NOT NULL,bpm REAL NOT NULL,bytes INTEGER,modified_ns INTEGER,corrected_utc TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS metadata_observation (path TEXT PRIMARY KEY,bytes INTEGER NOT NULL,modified_ns INTEGER NOT NULL,payload TEXT NOT NULL,inspected_utc TEXT NOT NULL)')
        db.execute("CREATE INDEX IF NOT EXISTS sample_name_path ON sample(name,path)")
        if args.operation == "search":
            rows = db.execute(
                "SELECT * FROM sample WHERE instr(lower(name), lower(?)) > 0 AND substr(name,1,2)!='._' ORDER BY name, path LIMIT ? OFFSET ?",
                (args.term, args.limit,args.offset),
            )
            result = [describe_sample(row, db) for row in rows]
        elif args.operation in {"measure", "correct-tempo","metadata"}:
            path = args.path.resolve()
            row = db.execute("SELECT * FROM sample WHERE path = ?", (str(path),)).fetchone()
            if row is None:
                parser.error("scan this sample before recording tempo")
            if args.operation=='metadata':
                from riff_metadata import observe
                before=path.stat()
                if (before.st_size,before.st_mtime_ns)!=(row['bytes'],row['modified_ns']):parser.error('sample changed since scan; rescan before reading metadata')
                observations=observe(path);after=path.stat()
                if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):parser.error('sample changed while reading metadata')
                db.execute('INSERT OR REPLACE INTO metadata_observation VALUES (?,?,?,?,?)',
                           (str(path),after.st_size,after.st_mtime_ns,json.dumps(observations,allow_nan=False),datetime.now(timezone.utc).isoformat()))
            elif args.operation == "measure":
                try:
                    before = path.stat()
                    if (before.st_mtime_ns, before.st_size) != (row["modified_ns"], row["bytes"]):
                        parser.error("sample changed since scan; rescan before measuring")
                    result = measure(path)
                    after = path.stat()
                    if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                        parser.error("sample changed during measurement")
                except (OSError, subprocess.SubprocessError) as error:
                    parser.error(f"tempo measurement failed: {error}")
                db.execute("INSERT OR REPLACE INTO tempo_measurement VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (str(path), before.st_mtime_ns, before.st_size, result["bpm"],
                            result["confidence"], result["source"], result["analyzed_seconds"]))
            else:
                if not 20 <= args.bpm <= 400:
                    parser.error("corrected BPM must be between 20 and 400")
                info=path.stat()
                if (info.st_size,info.st_mtime_ns)!=(row['bytes'],row['modified_ns']):parser.error('sample changed since scan; rescan before correcting')
                stamp=datetime.now(timezone.utc).isoformat()
                db.execute("INSERT OR REPLACE INTO tempo_correction(path,bpm,bytes,modified_ns,corrected_utc) VALUES (?,?,?,?,?)",
                           (str(path),args.bpm,info.st_size,info.st_mtime_ns,stamp))
                db.execute('INSERT INTO tempo_correction_history VALUES (?,?,?,?,?)',(str(path),args.bpm,info.st_size,info.st_mtime_ns,stamp))
            result = describe_sample(row, db)
        else:
            scanned = skipped = 0
            root = args.root.resolve()
            for path in ([root] if root.is_file() else root.rglob("*")):
                if path.suffix.lower() not in AUDIO or path.is_symlink() or path.name.startswith("._"):
                    continue
                try:
                    if not path.is_file():
                        continue
                    info = path.stat()
                    seconds = None
                    if not args.metadata_only and path.suffix.lower() == ".wav":
                        try:
                            with wave.open(str(path), "rb") as audio:
                                seconds = audio.getnframes() / audio.getframerate()
                        except (wave.Error, EOFError, OSError):
                            pass
                    db.execute(
                        """INSERT INTO sample VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(path) DO UPDATE SET name=excluded.name, bytes=excluded.bytes,
                        modified_ns=excluded.modified_ns,
                        seconds=CASE WHEN sample.modified_ns=excluded.modified_ns AND sample.bytes=excluded.bytes
                                     THEN coalesce(excluded.seconds, sample.seconds) ELSE excluded.seconds END,
                        duration_source=CASE WHEN sample.modified_ns=excluded.modified_ns AND sample.bytes=excluded.bytes
                                             THEN coalesce(excluded.duration_source, sample.duration_source)
                                             ELSE excluded.duration_source END""",
                        (str(path), path.name, info.st_size, info.st_mtime_ns,
                         seconds, "wav_header" if seconds is not None else None),
                    )
                    scanned += 1
                    if scanned % 100 == 0:
                        db.commit()
                except OSError:
                    skipped += 1
            result = {"indexed": scanned, "skipped": skipped}
    print(json.dumps(result))

if __name__ == "__main__":
    main()
