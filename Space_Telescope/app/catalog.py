"""관측 대상 목록과 가상 별 카탈로그.

가상 하늘은 1°x1° 타일 단위로 시드 고정 난수를 써서 생성하므로 항상 같은 별 배치가 나온다.
가상 카메라 렌더링과 Plate Solving이 같은 카탈로그를 사용한다.
"""
import math
from functools import lru_cache

import numpy as np

from .astro import angular_separation_deg

TARGETS = [
    {"name": "Sirius", "ra": 6.7525, "dec": -16.7161, "mag": -1.46, "type": "star"},
    {"name": "Vega", "ra": 18.6156, "dec": 38.7837, "mag": 0.03, "type": "star"},
    {"name": "Arcturus", "ra": 14.2610, "dec": 19.1825, "mag": -0.05, "type": "star"},
    {"name": "Rigel", "ra": 5.2423, "dec": -8.2016, "mag": 0.13, "type": "star"},
    {"name": "Betelgeuse", "ra": 5.9195, "dec": 7.4071, "mag": 0.50, "type": "star"},
    {"name": "Altair", "ra": 19.8464, "dec": 8.8683, "mag": 0.77, "type": "star"},
    {"name": "Antares", "ra": 16.4901, "dec": -26.4320, "mag": 1.06, "type": "star"},
    {"name": "Deneb", "ra": 20.6905, "dec": 45.2803, "mag": 1.25, "type": "star"},
    {"name": "Polaris", "ra": 2.5303, "dec": 89.2641, "mag": 1.98, "type": "star"},
    {"name": "M45 Pleiades", "ra": 3.7914, "dec": 24.1053, "mag": 1.6, "type": "cluster"},
    {"name": "M31 Andromeda", "ra": 0.7123, "dec": 41.2692, "mag": 3.4, "type": "galaxy"},
    {"name": "M42 Orion Nebula", "ra": 5.5881, "dec": -5.3911, "mag": 4.0, "type": "nebula"},
]

TILE_DEG = 1.0
STARS_PER_TILE = 70


def find_target(name):
    for t in TARGETS:
        if t["name"].lower() == name.lower():
            return t
    raise ValueError(f"알 수 없는 대상: {name}")


@lru_cache(maxsize=4096)
def _tile(ti, tj):
    seed = (ti * 1_000_003 + tj * 7_919 + 20_260_101) & 0xFFFFFFFF
    rng = np.random.default_rng(seed)
    # 타일 면적은 cos(Dec)에 비례하므로 별 개수도 비례시켜 하늘 전체 밀도를 균일하게 유지
    dec_lo = math.radians(-90 + tj * TILE_DEG)
    dec_hi = math.radians(-90 + (tj + 1) * TILE_DEG)
    area_factor = (math.sin(dec_hi) - math.sin(dec_lo)) / math.radians(TILE_DEG)
    n = max(1, int(round(STARS_PER_TILE * area_factor)))
    ra = (ti + rng.random(n)) * TILE_DEG
    # 면적 균일 분포가 되도록 sin(Dec)를 균일하게 샘플링
    dec = np.degrees(np.arcsin(math.sin(dec_lo) + (math.sin(dec_hi) - math.sin(dec_lo)) * rng.random(n)))
    mag = 6.0 + 8.0 * rng.random(n) ** 0.45  # 어두운 별이 더 많음
    return ra, dec, mag


def stars_in_region(ra_h, dec, radius_deg):
    """중심 (ra_h, dec) 반경 radius_deg 안의 별 (ra_deg, dec_deg, mag) 배열."""
    dec_lo = max(-90.0, dec - radius_deg)
    dec_hi = min(90.0, dec + radius_deg)
    tj_range = range(int(math.floor(dec_lo + 90)), min(179, int(math.floor(dec_hi + 90))) + 1)

    max_abs_dec = max(abs(dec_lo), abs(dec_hi))
    cos_d = math.cos(math.radians(min(max_abs_dec, 89.9)))
    ra_half = radius_deg / max(cos_d, 1e-3)
    ra0 = ra_h * 15
    if ra_half >= 180 or max_abs_dec > 89:
        ti_range = range(0, 360)
    else:
        ti_range = [ti % 360 for ti in range(int(math.floor(ra0 - ra_half)),
                                              int(math.floor(ra0 + ra_half)) + 1)]

    parts = [_tile(ti, tj) for tj in tj_range for ti in ti_range]
    ras = [p[0] for p in parts]
    decs = [p[1] for p in parts]
    mags = [p[2] for p in parts]
    ras.append(np.array([t["ra"] * 15 for t in TARGETS]))
    decs.append(np.array([t["dec"] for t in TARGETS]))
    mags.append(np.array([max(t["mag"], 2.0) for t in TARGETS]))
    ra_all, dec_all, mag_all = np.concatenate(ras), np.concatenate(decs), np.concatenate(mags)

    # 정확한 각거리로 필터링 (벡터화된 haversine)
    a1, d1 = math.radians(ra0), math.radians(dec)
    a2, d2 = np.radians(ra_all), np.radians(dec_all)
    s = np.sin((d2 - d1) / 2) ** 2 + math.cos(d1) * np.cos(d2) * np.sin((a2 - a1) / 2) ** 2
    sep = np.degrees(2 * np.arcsin(np.minimum(1.0, np.sqrt(s))))
    keep = sep <= radius_deg
    return ra_all[keep], dec_all[keep], mag_all[keep]


def targets_with_separation(ra_h, dec):
    out = []
    for t in TARGETS:
        out.append({**t, "separation_deg": round(angular_separation_deg(ra_h, dec, t["ra"], t["dec"]), 3)})
    return out
