"""ASCOM Alpaca 장비 (alpyca). Sky Simulator / ASCOM Omni-Simulator 등에 연결한다."""
import time

import numpy as np

from .. import config
from ..astro import validate_coords
from .base import DeviceError


def _wrap(fn, what):
    try:
        return fn()
    except DeviceError:
        raise
    except Exception as e:  # alpyca / 네트워크 예외를 통일
        raise DeviceError(f"{what} 실패: {e}") from e


class AlpacaTelescope:
    def __init__(self, host, port, device_number=0):
        from alpaca.telescope import Telescope
        self.address = f"{host}:{port}"
        self.name = f"Alpaca Telescope @ {self.address}"
        self._dev = Telescope(self.address, device_number)
        self.connected = False

    def connect(self):
        def _c():
            self._dev.Connected = True
            try:
                if self._dev.CanSetTracking:
                    self._dev.Tracking = True
            except Exception:
                pass
            self.name = f"{self._dev.Name} @ {self.address}"
        _wrap(_c, "망원경 연결")
        self.connected = True

    def disconnect(self):
        try:
            self._dev.Connected = False
        finally:
            self.connected = False

    def _require(self):
        if not self.connected:
            raise DeviceError("망원경이 연결되어 있지 않습니다.")

    def position(self):
        if not self.connected:
            return {"connected": False, "ra": None, "dec": None, "slewing": False, "tracking": False}
        return _wrap(lambda: {
            "connected": True,
            "ra": float(self._dev.RightAscension),
            "dec": float(self._dev.Declination),
            "slewing": bool(self._dev.Slewing),
            "tracking": bool(self._dev.Tracking),
        }, "위치 조회")

    def move(self, ra_h, dec):
        self._require()
        validate_coords(ra_h, dec)
        _wrap(lambda: self._dev.SlewToCoordinatesAsync(ra_h, dec), "이동 명령")
        return None

    def stop(self):
        self._require()
        _wrap(self._dev.AbortSlew, "정지 명령")


class AlpacaCamera:
    def __init__(self, host, port, device_number=0):
        from alpaca.camera import Camera
        self.address = f"{host}:{port}"
        self.name = f"Alpaca Camera @ {self.address}"
        self._dev = Camera(self.address, device_number)
        self.connected = False
        self.width = self.height = None
        self.pixel_scale = config.ALPACA_PIXEL_SCALE

    def connect(self):
        def _c():
            self._dev.Connected = True
            self.width = int(self._dev.CameraXSize)
            self.height = int(self._dev.CameraYSize)
            self.name = f"{self._dev.Name} @ {self.address}"
        _wrap(_c, "카메라 연결")
        self.connected = True

    def disconnect(self):
        try:
            self._dev.Connected = False
        finally:
            self.connected = False

    def info(self):
        return {"connected": self.connected, "width": self.width, "height": self.height,
                "pixel_scale": self.pixel_scale, "name": self.name}

    def capture(self, exposure):
        if not self.connected:
            raise DeviceError("카메라가 연결되어 있지 않습니다.")
        if not (0 < exposure <= 600):
            raise ValueError("노출 시간 범위가 올바르지 않습니다.")

        def _cap():
            self._dev.StartExposure(exposure, True)
            deadline = time.monotonic() + exposure + 60
            while not self._dev.ImageReady:
                if time.monotonic() > deadline:
                    raise DeviceError("촬영 시간 초과")
                time.sleep(0.2)
            arr = np.array(self._dev.ImageArray)
            if arr.ndim == 3:  # 컬러 -> 흑백
                arr = arr.mean(axis=2)
            arr = arr.T  # Alpaca ImageArray는 [x][y]
            return np.clip(arr, 0, 65535).astype(np.uint16)
        return _wrap(_cap, "촬영")
