"""OpenCV 기반 이미지 분석: 전처리, 별 탐지, 이동량 추적, Plate Solving."""
import math

import cv2
import numpy as np

from .astro import deproject, project
from .catalog import stars_in_region


def preprocess(img):
    """배경 제거 + 평활화. (배경 제거된 영상, 평활 영상, 잡음 표준편차) 반환."""
    f = img.astype(np.float32)
    bg = cv2.GaussianBlur(f, (0, 0), 25)
    sub = f - bg
    smooth = cv2.GaussianBlur(sub, (0, 0), 1.2)
    med = float(np.median(smooth))
    noise = 1.4826 * float(np.median(np.abs(smooth - med))) or 1.0
    return sub, smooth - med, noise


def detect_stars(img, sigma=5.0, min_area=3, max_stars=300):
    """별 탐지. 밝기 순으로 정렬된 [{x, y, flux, area, snr}] 반환."""
    sub, smooth, noise = preprocess(img)
    mask = (smooth > sigma * noise).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    stars = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        x0, y0 = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
        w, h = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        roi_lab = labels[y0:y0 + h, x0:x0 + w] == i
        roi = np.where(roi_lab, np.clip(sub[y0:y0 + h, x0:x0 + w], 0, None), 0)
        total = float(roi.sum())
        if total <= 0:
            continue
        yy, xx = np.mgrid[0:h, 0:w]
        cx = float((roi * xx).sum() / total) + x0
        cy = float((roi * yy).sum() / total) + y0
        peak = float(smooth[y0:y0 + h, x0:x0 + w][roi_lab].max())
        stars.append({"x": round(cx, 2), "y": round(cy, 2), "flux": round(total, 1),
                      "area": area, "snr": round(peak / noise, 1)})
    stars.sort(key=lambda s: s["flux"], reverse=True)
    return stars[:max_stars]


def track_shift(img_a, img_b):
    """두 이미지 사이 별의 이동량(px). 위상 상관(phase correlation) 사용."""
    _, a, _ = preprocess(img_a)
    _, b, _ = preprocess(img_b)
    if a.shape != b.shape:
        raise ValueError("두 이미지의 크기가 다릅니다.")
    win = cv2.createHanningWindow(a.shape[::-1], cv2.CV_32F)
    (dx, dy), response = cv2.phaseCorrelate(np.clip(a, 0, None), np.clip(b, 0, None), win)
    return {"dx": round(dx, 2), "dy": round(dy, 2),
            "distance": round(math.hypot(dx, dy), 2), "response": round(float(response), 3)}


def _catalog_pixels(hint_ra_h, hint_dec, width, height, scale_deg, margin_px, max_catalog):
    """hint 중심 접평면으로 투영한 카탈로그 별 픽셀 좌표 (밝은 순)."""
    cx, cy = width / 2, height / 2
    radius = math.hypot(width / 2 + margin_px, height / 2 + margin_px) * scale_deg
    ra, de, mag = stars_in_region(hint_ra_h, hint_dec, radius)
    xi, eta = project(ra, de, hint_ra_h * 15, hint_dec)
    cat = np.column_stack([cx + xi / scale_deg, cy - eta / scale_deg])
    inside = ((cat[:, 0] > -margin_px) & (cat[:, 0] < width + margin_px)
              & (cat[:, 1] > -margin_px) & (cat[:, 1] < height + margin_px))
    order = [i for i in np.argsort(mag) if inside[i]][:max_catalog]
    return cat[order]


def _match(det, cat, center, margin_px, thetas, bin_px=4.0):
    """회전각 후보마다 평행이동 벡터를 투표해 가장 일관된 (회전, 이동)을 찾는다.

    모델: det = R(theta) @ (cat - center) + center + t
    """
    best = None
    nb = int(2 * margin_px / bin_px) + 1
    for th in thetas:
        c, s = math.cos(th), math.sin(th)
        rot = (cat - center) @ np.array([[c, s], [-s, c]]) + center
        diffs = (det[:, None, :] - rot[None, :, :]).reshape(-1, 2)
        diffs = diffs[(np.abs(diffs) <= margin_px).all(axis=1)]
        if len(diffs) == 0:
            continue
        hist, xe, ye = np.histogram2d(diffs[:, 0], diffs[:, 1], bins=nb,
                                      range=[[-margin_px, margin_px], [-margin_px, margin_px]])
        hist = cv2.boxFilter(hist.astype(np.float32), -1, (2, 2), normalize=False)
        ix, iy = np.unravel_index(int(np.argmax(hist)), hist.shape)
        score = float(hist[ix, iy])
        if best is None or score > best[0]:
            best = (score, th, rot, np.array([xe[ix] + bin_px / 2, ye[iy] + bin_px / 2]))
    if best is None:
        return None
    _, th, rot, t = best
    pairs = []
    for tol in (8.0, 3.0):  # 2단계 정밀화
        cur = []
        for d in det:
            dist = np.linalg.norm(rot + t - d, axis=1)
            j = int(np.argmin(dist))
            if dist[j] < tol:
                cur.append(d - rot[j])
        if len(cur) < 4:
            break
        pairs = cur
        t = np.median(np.array(pairs), axis=0)
    return th, t, pairs


def plate_solve(stars, hint_ra_h, hint_dec, width, height, scale_arcsec,
                search_radius_deg=0.6, max_detected=40, max_catalog=120):
    """탐지된 별과 카탈로그를 대조해 이미지 중심의 실제 천구 좌표를 계산한다.

    1단계: hint(망원경이 보고한 좌표) 주변 카탈로그를 영상 좌표로 투영하고,
           회전각 후보별로 평행이동 벡터를 투표(histogram)해 대응 관계를 찾는다.
           (천구 극 근처에서는 작은 RA 차이도 시야 회전을 만들기 때문에 회전을 함께 탐색)
    2단계: 1단계 결과 좌표를 중심으로 다시 투영해 정밀하게 맞춘다.
    """
    scale_deg = scale_arcsec / 3600
    center = np.array([width / 2, height / 2])
    result = {"success": False, "matched": 0, "detected": len(stars)}
    if len(stars) < 4:
        result["message"] = "탐지된 별이 너무 적습니다 (최소 4개)."
        return result
    det = np.array([[s["x"], s["y"]] for s in stars[:max_detected]])

    margin = search_radius_deg / scale_deg
    cat = _catalog_pixels(hint_ra_h, hint_dec, width, height, scale_deg, margin, max_catalog)
    if len(cat) < 4:
        result["message"] = "주변 카탈로그 별이 부족합니다."
        return result

    rot_max = min(90.0, math.degrees(math.radians(search_radius_deg) * math.tan(
        math.radians(min(abs(hint_dec), 89.9)))) * 1.3 + 1.0)
    step = 1.0
    thetas = [0.0] if rot_max <= 1.0 else [math.radians(a) for a in np.arange(-rot_max, rot_max + step, step)]
    m = _match(det, cat, center, margin, thetas)
    if m is None or len(m[2]) < 4:
        result["message"] = f"일치하는 별이 부족합니다 ({0 if m is None else len(m[2])}개)."
        return result
    th, t, _ = m
    # 영상 중심이 hint 투영 평면에서 위치하는 픽셀: R(p - c) + c + t = c  =>  p = c - R^-1 t
    c_, s_ = math.cos(th), math.sin(th)
    p = center - np.array([[c_, s_], [-s_, c_]]) @ t  # R^-1 = R(-theta)
    ra1, dec1 = deproject((p[0] - center[0]) * scale_deg, -(p[1] - center[1]) * scale_deg,
                          hint_ra_h * 15, hint_dec)

    # 2단계: 새 중심에서 재투영 -> 회전/이동이 거의 0 이어야 함
    cat2 = _catalog_pixels(ra1 / 15, dec1, width, height, scale_deg, 40, max_catalog)
    m2 = _match(det, cat2, center, 40, [math.radians(a) for a in (-1, -0.5, 0, 0.5, 1)], bin_px=3.0)
    if m2 is None or len(m2[2]) < 4:
        result["message"] = "정밀 정합 실패"
        return result
    th2, t2, pairs = m2
    matched = len(pairs)
    result["matched"] = matched
    if matched < 0.25 * min(len(det), len(cat2)):
        result["message"] = f"일치하는 별이 부족합니다 ({matched}개)."
        return result
    resid = np.array(pairs) - t2
    rms = float(np.sqrt((resid ** 2).sum(axis=1).mean())) * scale_arcsec
    ra_deg, dec_deg = deproject(-t2[0] * scale_deg, t2[1] * scale_deg, ra1, dec1)

    # 보고 좌표 기준 영상 이동량(px): 프론트 표시용
    xi, eta = project(ra_deg, dec_deg, hint_ra_h * 15, hint_dec)
    result.update({
        "success": True,
        "ra": ra_deg / 15,
        "dec": dec_deg,
        "rotation_deg": round(math.degrees(th + th2), 2),
        "shift_px": {"dx": round(float(-xi) / scale_deg, 2), "dy": round(float(eta) / scale_deg, 2)},
        "rms_arcsec": round(rms, 2),
        "message": f"{matched}개 별 일치",
    })
    return result
