"""장비 연결 관리."""
import threading

from .base import DeviceError
from .sim import SimCamera, SimTelescope

__all__ = ["DeviceError", "DeviceManager"]


class DeviceManager:
    def __init__(self):
        self.mode = None
        self.telescope = None
        self.camera = None
        self.lock = threading.RLock()

    @property
    def connected(self):
        return bool(self.telescope and self.telescope.connected)

    def connect(self, mode="sim", host=None, port=None):
        with self.lock:
            if self.connected:
                self.disconnect()
            if mode == "sim":
                tel = SimTelescope()
                cam = SimCamera(tel)
            elif mode == "alpaca":
                from .alpaca import AlpacaCamera, AlpacaTelescope
                tel = AlpacaTelescope(host, port)
                cam = AlpacaCamera(host, port)
            else:
                raise ValueError("mode는 'sim' 또는 'alpaca'여야 합니다.")
            tel.connect()
            try:
                cam.connect()
            except Exception:
                tel.disconnect()
                raise
            self.mode, self.telescope, self.camera = mode, tel, cam
            return self.status()

    def disconnect(self):
        with self.lock:
            for dev in (self.camera, self.telescope):
                if dev is not None:
                    try:
                        dev.disconnect()
                    except Exception:
                        pass
            self.mode = self.telescope = self.camera = None

    def require(self):
        if not self.connected:
            raise DeviceError("장비가 연결되어 있지 않습니다. 먼저 /telescope/connect 를 호출하세요.")
        return self.telescope, self.camera

    def status(self):
        if not self.connected:
            return {"connected": False, "mode": None, "telescope": None, "camera": None}
        return {
            "connected": True,
            "mode": self.mode,
            "telescope": self.telescope.name,
            "camera": self.camera.info(),
        }
