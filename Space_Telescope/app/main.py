"""Space Telescope API."""
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, vision
from .astro import format_dec, format_ra
from .automation import JobManager, Pipeline
from .catalog import TARGETS, find_target, targets_with_separation
from .devices import DeviceError, DeviceManager
from .logs import logger, memory_handler
from .storage import ImageStore

app = FastAPI(title="Space Telescope API", version="1.0.0",
              description="가상 천체망원경 제어 및 자동 관측 시스템")

devices = DeviceManager()
store = ImageStore()
jobs = JobManager(devices, store)


@app.exception_handler(DeviceError)
async def device_error_handler(_: Request, exc: DeviceError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------- 요청 모델 ----------
class ConnectRequest(BaseModel):
    mode: Literal["sim", "alpaca"] = Field(default=config.DEVICE_MODE)
    host: str = config.ALPACA_HOST
    port: int = config.ALPACA_PORT


class MoveRequest(BaseModel):
    target: Optional[str] = Field(None, description="대상 이름 (ra/dec 대신 사용)")
    ra: Optional[float] = Field(None, ge=0, lt=24, description="적경 (시간)")
    dec: Optional[float] = Field(None, ge=-90, le=90, description="적위 (도)")


class CaptureRequest(BaseModel):
    exposure: float = Field(1.0, gt=0, le=600)
    analyze: bool = True


class TrackRequest(BaseModel):
    image_a: str
    image_b: str


class CorrectionRequest(MoveRequest):
    exposure: float = Field(1.0, gt=0, le=60)
    tolerance_arcsec: float = Field(config.CORRECTION_TOLERANCE_ARCSEC, gt=0)
    max_iterations: int = Field(4, ge=1, le=10)


class ObservationRequest(BaseModel):
    targets: List[str] = Field(..., min_length=1)
    exposure: float = Field(1.0, gt=0, le=60, description="보정용 노출 (s)")
    final_exposure: float = Field(3.0, gt=0, le=600, description="최종 관측 노출 (s)")
    tolerance_arcsec: float = Field(config.CORRECTION_TOLERANCE_ARCSEC, gt=0)
    max_iterations: int = Field(4, ge=1, le=10)


def resolve_target(req: MoveRequest):
    if req.target:
        t = find_target(req.target)
        return t["name"], t["ra"], t["dec"]
    if req.ra is None or req.dec is None:
        raise ValueError("target 또는 ra/dec 를 지정하세요.")
    return None, req.ra, req.dec


def position_payload():
    if not devices.connected:
        return {"connected": False}
    p = devices.telescope.position()
    if p.get("ra") is not None:
        p["ra_text"] = format_ra(p["ra"])
        p["dec_text"] = format_dec(p["dec"])
    return p


# ---------- 상태 ----------
@app.get("/health")
def health():
    return {"message": "Space Telescope API Running"}


@app.get("/status")
def status():
    return {"devices": devices.status(), "position": position_payload(), "job": jobs.status()}


# ---------- 망원경 ----------
@app.post("/telescope/connect")
def telescope_connect(req: ConnectRequest = ConnectRequest()):
    if jobs.running:
        raise DeviceError("자동 작업 실행 중에는 재연결할 수 없습니다.")
    st = devices.connect(req.mode, req.host, req.port)
    logger.info(f"[장비] 연결됨: {st['telescope']} / {st['camera']['name']}")
    return st


@app.post("/telescope/disconnect")
def telescope_disconnect():
    if jobs.running:
        raise DeviceError("자동 작업 실행 중에는 연결을 해제할 수 없습니다.")
    devices.disconnect()
    logger.info("[장비] 연결 해제")
    return devices.status()


@app.get("/telescope/position")
def telescope_position():
    devices.require()
    return position_payload()


@app.post("/telescope/move")
def telescope_move(req: MoveRequest):
    tel, _ = devices.require()
    if jobs.running:
        raise DeviceError("자동 작업 실행 중에는 수동 이동할 수 없습니다.")
    name, ra, dec = resolve_target(req)
    duration = tel.move(ra, dec)
    logger.info(f"[망원경] 이동: {name or ''} RA={ra:.4f}h Dec={dec:+.4f}°")
    return {"target": name, "ra": ra, "dec": dec, "estimated_seconds": duration}


@app.post("/telescope/stop")
def telescope_stop():
    tel, _ = devices.require()
    tel.stop()
    logger.info("[망원경] 정지")
    return position_payload()


@app.get("/targets")
def targets():
    if devices.connected:
        p = devices.telescope.position()
        if p.get("ra") is not None:
            return targets_with_separation(p["ra"], p["dec"])
    return TARGETS


# ---------- 카메라 / 이미지 ----------
@app.post("/camera/capture")
def camera_capture(req: CaptureRequest = CaptureRequest()):
    devices.require()
    if jobs.running:
        raise DeviceError("자동 작업 실행 중에는 수동 촬영할 수 없습니다.")
    pipe = Pipeline(devices, store)
    img, meta = pipe.capture(req.exposure)
    logger.info(f"[카메라] 촬영 {meta['id']} ({req.exposure}s)")
    if req.analyze:
        stars, solve = pipe.analyze(img, meta)
        logger.info(f"[분석] 별 {len(stars)}개, Plate Solving {'성공' if solve['success'] else '실패'}")
    return store.meta(meta["id"])


def _get_meta(image_id):
    try:
        return store.meta(image_id)
    except KeyError:
        raise HTTPException(404, "이미지를 찾을 수 없습니다.")


@app.get("/images")
def images(limit: int = 50):
    return store.list(limit)


@app.get("/images/{image_id}")
def image_meta(image_id: str):
    return _get_meta(image_id)


@app.get("/images/{image_id}/png")
def image_png(image_id: str):
    _get_meta(image_id)
    return FileResponse(store.path(image_id, "png"), media_type="image/png")


@app.get("/images/{image_id}/fits")
def image_fits(image_id: str):
    _get_meta(image_id)
    return FileResponse(store.path(image_id, "fits"), media_type="application/fits",
                        filename=f"{image_id}.fits")


# ---------- 컴퓨터 비전 ----------
@app.post("/vision/analyze/{image_id}")
def vision_analyze(image_id: str):
    meta = _get_meta(image_id)
    img = store.load(image_id)
    stars = vision.detect_stars(img)
    scale = devices.camera.pixel_scale if devices.connected else config.SIM_PIXEL_SCALE
    solve = vision.plate_solve(stars, meta["ra"], meta["dec"], img.shape[1], img.shape[0], scale)
    analysis = {"star_count": len(stars), "solve": solve}
    return store.update_meta(image_id, stars=stars[:200], analysis=analysis)


@app.post("/vision/track")
def vision_track(req: TrackRequest):
    _get_meta(req.image_a)
    _get_meta(req.image_b)
    return vision.track_shift(store.load(req.image_a), store.load(req.image_b))


# ---------- 자동 보정 / 자동 관측 ----------
@app.post("/correction/run")
def correction_run(req: CorrectionRequest):
    name, ra, dec = resolve_target(req)
    target = {"name": name or f"RA {ra:.3f}h / Dec {dec:+.3f}°", "ra": ra, "dec": dec}
    return jobs.start("correction", [target], exposure=req.exposure,
                      tolerance=req.tolerance_arcsec, max_iter=req.max_iterations)


@app.post("/observation/start")
def observation_start(req: ObservationRequest):
    targets = [find_target(n) for n in req.targets]
    return jobs.start("observation", targets, exposure=req.exposure, final_exposure=req.final_exposure,
                      tolerance=req.tolerance_arcsec, max_iter=req.max_iterations)


@app.get("/observation/status")
def observation_status():
    return jobs.status()


@app.post("/observation/cancel")
def observation_cancel():
    jobs.cancel()
    return jobs.status()


@app.get("/logs")
def logs(after: int = 0, limit: int = 200):
    return memory_handler.get(after, limit)


# ---------- 프론트엔드 ----------
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(config.FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")
