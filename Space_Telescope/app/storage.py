"""촬영 이미지 저장소: FITS(원본 16bit) + PNG(미리보기) + JSON(메타데이터)."""
import json
import threading
import uuid
from datetime import datetime, timezone

import cv2
import numpy as np

from . import config


def write_fits(path, img, header):
    """astropy 없이 16bit 흑백 FITS 파일을 기록한다."""
    h, w = img.shape
    cards = [
        ("SIMPLE", True, "conforms to FITS standard"),
        ("BITPIX", 16, "16-bit signed integers"),
        ("NAXIS", 2, ""),
        ("NAXIS1", w, "width"),
        ("NAXIS2", h, "height"),
        ("BZERO", 32768, "unsigned 16-bit offset"),
        ("BSCALE", 1, ""),
    ] + [(k[:8].upper(), v, c) for k, v, c in header]

    def card(k, v, c):
        if isinstance(v, bool):
            val = "T" if v else "F"
            s = f"{k:<8}= {val:>20}"
        elif isinstance(v, (int, float)):
            s = f"{k:<8}= {v:>20}"
        else:
            s = f"{k:<8}= '{str(v)[:60]}'"
        if c:
            s += f" / {c}"
        return s[:80].ljust(80)

    text = "".join(card(*c) for c in cards) + "END".ljust(80)
    text = text.ljust(((len(text) + 2879) // 2880) * 2880)
    # FITS는 첫 행이 아래쪽이므로 상하 반전
    data = (np.flipud(img).astype(np.int32) - 32768).astype(">i2").tobytes()
    data += b"\0" * ((2880 - len(data) % 2880) % 2880)
    with open(path, "wb") as f:
        f.write(text.encode("ascii"))
        f.write(data)


def read_fits(path):
    with open(path, "rb") as f:
        raw = f.read()
    hdr = {}
    off = 0
    while True:
        block = raw[off:off + 2880].decode("ascii")
        off += 2880
        done = False
        for i in range(0, 2880, 80):
            c = block[i:i + 80]
            if c.startswith("END"):
                done = True
                break
            if "=" in c[:10]:
                hdr[c[:8].strip()] = c[10:].split("/")[0].strip().strip("'").strip()
        if done:
            break
    w, h = int(hdr["NAXIS1"]), int(hdr["NAXIS2"])
    arr = np.frombuffer(raw[off:off + w * h * 2], dtype=">i2").reshape(h, w)
    return np.flipud((arr.astype(np.int32) + 32768).astype(np.uint16))


def stretch_to_png(img):
    f = img.astype(np.float32)
    lo = float(np.percentile(f, 50))
    hi = float(np.percentile(f, 99.9))
    a = np.clip((f - lo) / max(hi - lo, 1.0), 0, 1)
    a = np.arcsinh(8 * a) / np.arcsinh(8)
    return (a * 255).astype(np.uint8)


class ImageStore:
    def __init__(self, directory=None):
        self.dir = directory or config.IMAGE_DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def save(self, img, meta):
        image_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        meta = {"id": image_id, "created_at": now, "width": int(img.shape[1]),
                "height": int(img.shape[0]), **meta}
        header = [("DATE-OBS", now, "UTC"), ("EXPTIME", float(meta.get("exposure", 0)), "s"),
                  ("OBJECT", meta.get("target") or "", ""),
                  ("RA", round(float(meta.get("ra") or 0) * 15, 6), "deg (reported)"),
                  ("DEC", round(float(meta.get("dec") or 0), 6), "deg (reported)")]
        with self._lock:
            write_fits(self.dir / f"{image_id}.fits", img, header)
            cv2.imwrite(str(self.dir / f"{image_id}.png"), stretch_to_png(img))
            (self.dir / f"{image_id}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                                       encoding="utf-8")
        return meta

    def _check(self, image_id):
        if not image_id.replace("-", "").isalnum():
            raise KeyError(image_id)
        if not (self.dir / f"{image_id}.json").exists():
            raise KeyError(image_id)

    def meta(self, image_id):
        self._check(image_id)
        return json.loads((self.dir / f"{image_id}.json").read_text(encoding="utf-8"))

    def update_meta(self, image_id, **fields):
        with self._lock:
            m = self.meta(image_id)
            m.update(fields)
            (self.dir / f"{image_id}.json").write_text(json.dumps(m, ensure_ascii=False, indent=2),
                                                       encoding="utf-8")
            return m

    def load(self, image_id):
        self._check(image_id)
        return read_fits(self.dir / f"{image_id}.fits")

    def path(self, image_id, ext):
        self._check(image_id)
        return self.dir / f"{image_id}.{ext}"

    def list(self, limit=50):
        files = sorted(self.dir.glob("*.json"), reverse=True)[:limit]
        out = []
        for f in files:
            m = json.loads(f.read_text(encoding="utf-8"))
            m.pop("stars", None)
            out.append(m)
        return out
