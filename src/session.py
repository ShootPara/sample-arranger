"""Bounded disposable generated-chunk playback lifecycle."""
import queue
import threading
import wave
import time


class ContinuousSession:
    def __init__(self, root, generate, consume, *, ahead=2, wait_seconds=90,
                 max_chunk_bytes=24_000_000, max_chunk_seconds=None):
        if not 1 <= ahead <= 3 or wait_seconds <= 0:
            raise ValueError("invalid buffer settings")
        self.root, self.generate, self.consume = root, generate, consume
        self.buffer = queue.Queue(maxsize=ahead)
        self.stop = threading.Event()
        self.wait_seconds = wait_seconds
        self.error = None
        self.max_chunk_bytes = max_chunk_bytes
        self.max_chunk_seconds = max_chunk_seconds
        self.generated=0
        self.completed=0
        self.error_lock=threading.Lock()

    def cancel(self):
        self.stop.set()

    def fail(self,error):
        with self.error_lock:
            if self.error is None:self.error=error
        self.stop.set()

    def _produce(self, count):
        try:
            for index in range(count):
                if self.stop.is_set():
                    break
                path = self.root / f"chunk-{index}.wav"
                self.generate(index, path, self.stop)
                if self.stop.is_set():
                    break
                if path.exists() and path.stat().st_size > self.max_chunk_bytes:
                    raise ValueError("continuous chunk byte cap exceeded")
                if self.max_chunk_seconds is not None and path.exists():
                    with wave.open(str(path)) as audio:
                        if audio.getnframes() / audio.getframerate() > self.max_chunk_seconds:
                            raise ValueError("continuous chunk duration cap exceeded")
                self.generated+=1
                while not self.stop.is_set():
                    try:
                        self.buffer.put(path, timeout=0.1)
                        break
                    except queue.Full:
                        continue
        except Exception as error:
            self.fail(error)

    def run(self, count):
        if count < 1:
            raise ValueError("chunk count must be positive")
        producer = threading.Thread(target=self._produce, args=(count,), daemon=True)
        producer.start()
        try:
            for _ in range(count):
                if self.stop.is_set():
                    break
                deadline = time.monotonic() + self.wait_seconds
                path = None
                while not self.stop.is_set() and path is None:
                    try:
                        path = self.buffer.get(timeout=min(0.1, self.wait_seconds))
                    except queue.Empty:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("continuous audio underrun")
                if path is None:
                    break
                try:
                    if not self.stop.is_set():
                        self.consume(path, self.stop)
                        if not self.stop.is_set():self.completed+=1
                finally:
                    path.unlink(missing_ok=True)
            if self.error:
                raise self.error
        finally:
            self.cancel()
            producer.join(timeout=self.wait_seconds)
            if producer.is_alive():
                raise TimeoutError("chunk generator did not stop within deadline")
            for path in self.root.glob("chunk-*.wav"):
                path.unlink()
