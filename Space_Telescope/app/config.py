"""환경 변수 기반 설정."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
IMAGE_DIR = DATA_DIR / "images"
LOG_DIR = DATA_DIR / "logs"
FRONTEND_DIR = BASE_DIR / "frontend"

# sim: 내장 가상 망원경/카메라, alpaca: ASCOM Alpaca 장비(Sky Simulator 등)
DEVICE_MODE = os.getenv("DEVICE_MODE", "sim")
ALPACA_HOST = os.getenv("ALPACA_HOST", "127.0.0.1")
ALPACA_PORT = int(os.getenv("ALPACA_PORT", "32323"))
ALPACA_PIXEL_SCALE = float(os.getenv("ALPACA_PIXEL_SCALE", "4.5"))  # arcsec/px

# 가상 장비 파라미터
SIM_SLEW_RATE_DEG = float(os.getenv("SIM_SLEW_RATE_DEG", "8"))  # deg/s
SIM_EXPOSURE_DELAY = float(os.getenv("SIM_EXPOSURE_DELAY", "1"))  # 노출 시간 대비 실제 대기 비율
SIM_WIDTH = 800
SIM_HEIGHT = 600
SIM_PIXEL_SCALE = 4.5  # arcsec/px  -> 시야 1.0 x 0.75 deg

CORRECTION_TOLERANCE_ARCSEC = float(os.getenv("CORRECTION_TOLERANCE_ARCSEC", "30"))
