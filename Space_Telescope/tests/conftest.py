import os
import sys
import tempfile
from pathlib import Path

# 테스트는 빠르게: 즉시 이동, 노출 대기 없음, 임시 데이터 폴더
os.environ.setdefault("SIM_SLEW_RATE_DEG", "1000")
os.environ.setdefault("SIM_EXPOSURE_DELAY", "0")
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="space-telescope-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
