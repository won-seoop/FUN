"""천문 좌표 계산 유틸리티 (RA: 시간 단위, Dec: 도 단위)."""
import math

import numpy as np


def angular_separation_deg(ra1_h, dec1, ra2_h, dec2):
    """두 천체 사이의 각거리(도)."""
    a1, d1 = math.radians(ra1_h * 15), math.radians(dec1)
    a2, d2 = math.radians(ra2_h * 15), math.radians(dec2)
    s = (math.sin((d2 - d1) / 2) ** 2
         + math.cos(d1) * math.cos(d2) * math.sin((a2 - a1) / 2) ** 2)
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(s))))


def project(ra_deg, dec_deg, ra0_deg, dec0_deg):
    """Gnomonic(접평면) 투영. 결과 (xi, eta)는 도 단위."""
    a = np.radians(np.asarray(ra_deg, dtype=float))
    d = np.radians(np.asarray(dec_deg, dtype=float))
    a0, d0 = math.radians(ra0_deg), math.radians(dec0_deg)
    cosc = np.sin(d0) * np.sin(d) + np.cos(d0) * np.cos(d) * np.cos(a - a0)
    xi = np.cos(d) * np.sin(a - a0) / cosc
    eta = (np.cos(d0) * np.sin(d) - np.sin(d0) * np.cos(d) * np.cos(a - a0)) / cosc
    return np.degrees(xi), np.degrees(eta)


def deproject(xi_deg, eta_deg, ra0_deg, dec0_deg):
    """접평면 좌표 -> (ra_deg, dec_deg)."""
    xi, eta = math.radians(xi_deg), math.radians(eta_deg)
    a0, d0 = math.radians(ra0_deg), math.radians(dec0_deg)
    rho = math.hypot(xi, eta)
    if rho == 0:
        return ra0_deg % 360, dec0_deg
    c = math.atan(rho)
    dec = math.asin(math.cos(c) * math.sin(d0) + eta * math.sin(c) * math.cos(d0) / rho)
    ra = a0 + math.atan2(xi * math.sin(c),
                         rho * math.cos(d0) * math.cos(c) - eta * math.sin(d0) * math.sin(c))
    return math.degrees(ra) % 360, math.degrees(dec)


def offset_position(ra_h, dec, xi_deg, eta_deg):
    """(ra_h, dec)에서 접평면 오프셋만큼 이동한 좌표 (ra_h, dec)."""
    ra_deg, dec_deg = deproject(xi_deg, eta_deg, ra_h * 15, dec)
    return ra_deg / 15, dec_deg


def format_ra(ra_h):
    total = round((ra_h % 24) * 3600, 1)
    h = int(total // 3600)
    m = int((total % 3600) // 60)
    s = total % 60
    return f"{h:02d}h {m:02d}m {s:04.1f}s"


def format_dec(dec):
    sign = "-" if dec < 0 else "+"
    total = round(abs(dec) * 3600)
    d = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{sign}{d:02d}° {m:02d}' {s:02d}\""


def validate_coords(ra_h, dec):
    if not (0 <= ra_h < 24):
        raise ValueError("RA는 0 이상 24 미만(시간)이어야 합니다.")
    if not (-90 <= dec <= 90):
        raise ValueError("Dec는 -90 ~ +90(도) 범위여야 합니다.")
