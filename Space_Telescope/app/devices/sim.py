"""내장 가상 망원경 / 카메라.

가상 망원경은 실제 장비처럼 '마운트 모델 오차'(고정 오프셋 + 매 이동마다 작은 무작위 오차)를 가진다.
즉 보고되는 좌표와 실제로 향한 방향이 다르며, 촬영 이미지를 분석해야 실제 방향을 알 수 있다.
"""
import math
import threading
import time

import numpy as np

from .. import config
from ..astro import angular_separation_deg, offset_position, project, validate_coords
from ..catalog import stars_in_region
from .base import DeviceError


class SimTelescope:
    name = "Virtual Telescope (built-in)"

    def __init__(self, slew_rate_deg=None, seed=None):
        self.slew_rate = slew_rate_deg or config.SIM_SLEW_RATE_DEG
        self.rng = np.random.default_rng(seed)
        self.connected = False
        self._lock = threading.Lock()
        self._ra, self._dec = 0.0, 45.0
        self._slew = None  # (start_ra, start_dec, end_ra, end_dec, t0, duration)
        # 고정 마운트 오차 (접평면 오프셋, 도). 크기 0.1~0.25°
        ang = self.rng.uniform(0, 2 * math.pi)
        mag = self.rng.uniform(0.10, 0.25)
        self.model_error = (mag * math.cos(ang), mag * math.sin(ang))
        self._jitter = (0.0, 0.0)

    # --- 내부 ---
    def _update(self):
        if self._slew is None:
            return
        sra, sdec, era, edec, t0, dur = self._slew
        frac = 1.0 if dur <= 0 else min(1.0, (time.monotonic() - t0) / dur)
        dra = ((era - sra + 12) % 24) - 12  # 최단 경로
        self._ra = (sra + dra * frac) % 24
        self._dec = sdec + (edec - sdec) * frac
        if frac >= 1.0:
            self._ra, self._dec = era, edec
            self._slew = None

    def _require(self):
        if not self.connected:
            raise DeviceError("망원경이 연결되어 있지 않습니다.")

    # --- 공개 API ---
    def connect(self):
        self.connected = True

    def disconnect(self):
        with self._lock:
            self._update()
            self._slew = None
        self.connected = False

    def position(self):
        with self._lock:
            self._update()
            return {
                "connected": self.connected,
                "ra": self._ra,
                "dec": self._dec,
                "slewing": self._slew is not None,
                "tracking": self.connected,
            }

    def move(self, ra_h, dec):
        self._require()
        validate_coords(ra_h, dec)
        with self._lock:
            self._update()
            dist = angular_separation_deg(self._ra, self._dec, ra_h, dec)
            dur = dist / self.slew_rate
            self._slew = (self._ra, self._dec, ra_h, dec, time.monotonic(), dur)
            sigma = 8 / 3600  # 이동마다 약 8 arcsec 무작위 오차
            self._jitter = tuple(self.rng.normal(0, sigma, 2))
        return dur

    def stop(self):
        self._require()
        with self._lock:
            self._update()
            self._slew = None

    def true_pointing(self):
        """실제로 망원경이 향하고 있는 방향 (가상 카메라 렌더링용)."""
        p = self.position()
        dx = self.model_error[0] + self._jitter[0]
        dy = self.model_error[1] + self._jitter[1]
        return offset_position(p["ra"], p["dec"], dx, dy)


def render_starfield(ra_h, dec, width, height, scale_arcsec, exposure, rng):
    """(ra_h, dec)를 중심으로 하는 가상 별 사진 (uint16)."""
    scale_deg = scale_arcsec / 3600
    radius = math.hypot(width, height) / 2 * scale_deg * 1.05
    ra, de, mag = stars_in_region(ra_h, dec, radius)
    xi, eta = project(ra, de, ra_h * 15, dec)
    xs = width / 2 + xi / scale_deg
    ys = height / 2 - eta / scale_deg

    img = np.zeros((height, width), dtype=np.float32)
    psf = 1.6
    r = int(psf * 5)
    amps = 20000.0 * exposure * 10 ** (-0.4 * (mag - 6.0))
    for x, y, amp in zip(xs, ys, amps):
        if not (-r <= x < width + r and -r <= y < height + r):
            continue
        x0, x1 = max(0, int(x) - r), min(width, int(x) + r + 1)
        y0, y1 = max(0, int(y) - r), min(height, int(y) + r + 1)
        if x0 >= x1 or y0 >= y1:
            continue
        gx = np.arange(x0, x1) - x
        gy = np.arange(y0, y1) - y
        img[y0:y1, x0:x1] += amp * np.exp(-(gy[:, None] ** 2 + gx[None, :] ** 2) / (2 * psf ** 2))

    bg = 300.0 * exposure + 100.0
    noise = rng.normal(0, math.sqrt(bg) + 4.0, img.shape).astype(np.float32)
    img += bg + noise
    return np.clip(img, 0, 65535).astype(np.uint16)


class SimCamera:
    name = "Virtual Camera (built-in)"

    def __init__(self, telescope: SimTelescope, seed=None):
        self.telescope = telescope
        self.rng = np.random.default_rng(seed)
        self.connected = False
        self.width = config.SIM_WIDTH
        self.height = config.SIM_HEIGHT
        self.pixel_scale = config.SIM_PIXEL_SCALE

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def info(self):
        return {"connected": self.connected, "width": self.width, "height": self.height,
                "pixel_scale": self.pixel_scale, "name": self.name}

    def capture(self, exposure):
        if not self.connected:
            raise DeviceError("카메라가 연결되어 있지 않습니다.")
        if not (0 < exposure <= 60):
            raise ValueError("노출 시간은 0초 초과 60초 이하여야 합니다.")
        if self.telescope.position()["slewing"]:
            raise DeviceError("망원경이 이동 중입니다. 이동이 끝난 뒤 촬영하세요.")
        time.sleep(exposure * config.SIM_EXPOSURE_DELAY)
        ra, dec = self.telescope.true_pointing()
        return render_starfield(ra, dec, self.width, self.height, self.pixel_scale, exposure, self.rng)
