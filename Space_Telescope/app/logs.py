"""관측 로그: 메모리 링버퍼(프론트 표시용) + 파일."""
import logging
import threading
from collections import deque
from datetime import datetime

from . import config


class MemoryHandler(logging.Handler):
    def __init__(self, capacity=500):
        super().__init__()
        self.records = deque(maxlen=capacity)
        self.seq = 0
        self._lock = threading.Lock()

    def emit(self, record):
        with self._lock:
            self.seq += 1
            self.records.append({
                "seq": self.seq,
                "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "level": record.levelname,
                "message": record.getMessage(),
            })

    def get(self, after=0, limit=200):
        with self._lock:
            items = [r for r in self.records if r["seq"] > after]
        return items[-limit:]


memory_handler = MemoryHandler()
logger = logging.getLogger("telescope")
logger.setLevel(logging.INFO)
logger.addHandler(memory_handler)
logger.propagate = False

try:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    _fh = logging.FileHandler(config.LOG_DIR / "observation.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(_fh)
except OSError:
    pass
