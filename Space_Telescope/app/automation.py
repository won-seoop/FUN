"""자동 위치 보정과 자동 관측 작업.

작업은 백그라운드 스레드에서 실행되며 /observation/status 로 진행 상황을 조회한다.
"""
import threading
import time
import traceback
from datetime import datetime

from . import config, vision
from .astro import angular_separation_deg, offset_position, project
from .devices import DeviceError
from .logs import logger


class Cancelled(Exception):
    pass


class Pipeline:
    """장비 + 저장소를 이용한 단위 동작 (이동 대기, 촬영, 분석)."""

    def __init__(self, devices, store, cancel_event=None):
        self.devices = devices
        self.store = store
        self.cancel = cancel_event or threading.Event()

    def check(self):
        if self.cancel.is_set():
            raise Cancelled()

    def slew_and_wait(self, ra, dec, timeout=180):
        tel, _ = self.devices.require()
        tel.move(ra, dec)
        t0 = time.monotonic()
        time.sleep(0.05)
        while tel.position()["slewing"]:
            self.check()
            if time.monotonic() - t0 > timeout:
                raise DeviceError("이동 시간 초과")
            time.sleep(0.2)
        time.sleep(0.2)  # 안정화

    def capture(self, exposure, target=None, purpose="manual"):
        tel, cam = self.devices.require()
        self.check()
        pos = tel.position()
        img = cam.capture(exposure)
        meta = self.store.save(img, {"exposure": exposure, "ra": pos["ra"], "dec": pos["dec"],
                                     "target": target, "purpose": purpose, "mode": self.devices.mode,
                                     "pixel_scale": cam.pixel_scale})
        return img, meta

    def analyze(self, img, meta):
        _, cam = self.devices.require()
        stars = vision.detect_stars(img)
        solve = vision.plate_solve(stars, meta["ra"], meta["dec"], img.shape[1], img.shape[0],
                                   cam.pixel_scale)
        analysis = {"star_count": len(stars), "solve": solve}
        self.store.update_meta(meta["id"], stars=stars[:200], analysis=analysis)
        return stars, solve


def correct_to_target(pipe, name, ra, dec, exposure=1.0, tolerance=None, max_iter=4, on_step=None):
    """목표 좌표로 이동한 뒤 촬영-분석-보정을 반복해 실제 방향을 목표에 맞춘다."""
    tolerance = tolerance or config.CORRECTION_TOLERANCE_ARCSEC
    on_step = on_step or (lambda *_: None)
    iterations = []
    cmd_ra, cmd_dec = ra, dec
    logger.info(f"[보정] {name}: 목표 RA={ra:.4f}h Dec={dec:+.4f}° 로 이동")
    on_step("slewing")
    pipe.slew_and_wait(cmd_ra, cmd_dec)

    success = False
    for i in range(1, max_iter + 1):
        pipe.check()
        on_step(f"capture #{i}")
        img, meta = pipe.capture(exposure, target=name, purpose=f"correction-{i}")
        on_step(f"analyze #{i}")
        stars, solve = pipe.analyze(img, meta)
        if not solve["success"]:
            logger.warning(f"[보정] {name} #{i}: Plate Solving 실패 - {solve.get('message')}")
            iterations.append({"iteration": i, "image_id": meta["id"], "solved": False,
                               "message": solve.get("message"), "stars": len(stars)})
            break
        err = angular_separation_deg(ra, dec, solve["ra"], solve["dec"]) * 3600
        # 실제 방향(solve) 기준 목표의 접평면 오프셋 -> 명령 좌표에 그대로 더해 보정
        xi, eta = project(ra * 15, dec, solve["ra"] * 15, solve["dec"])
        xi, eta = float(xi), float(eta)
        iterations.append({
            "iteration": i, "image_id": meta["id"], "solved": True, "stars": len(stars),
            "matched": solve["matched"], "command_ra": cmd_ra, "command_dec": cmd_dec,
            "solved_ra": solve["ra"], "solved_dec": solve["dec"],
            "error_arcsec": round(err, 1), "error_ra_arcsec": round(xi * 3600, 1),
            "error_dec_arcsec": round(eta * 3600, 1),
        })
        logger.info(f"[보정] {name} #{i}: 오차 {err:.1f}\" (별 {len(stars)}개, 일치 {solve['matched']}개)")
        if err <= tolerance:
            success = True
            break
        if i == max_iter:
            break
        cmd_ra, cmd_dec = offset_position(cmd_ra, cmd_dec, xi, eta)
        on_step(f"correcting #{i}")
        logger.info(f"[보정] {name}: 보정 이동 RA={cmd_ra:.4f}h Dec={cmd_dec:+.4f}°")
        pipe.slew_and_wait(cmd_ra, cmd_dec)

    final_err = iterations[-1].get("error_arcsec") if iterations else None
    if success:
        logger.info(f"[보정] {name}: 보정 완료 - 최종 오차 {final_err}\" (허용 {tolerance}\")")
    else:
        logger.warning(f"[보정] {name}: 허용 오차 내로 보정하지 못했습니다 (최종 {final_err}\")")
    return {"target": name, "ra": ra, "dec": dec, "success": success, "verified": success,
            "tolerance_arcsec": tolerance, "final_error_arcsec": final_err, "iterations": iterations}


class JobManager:
    """한 번에 하나의 자동 작업(보정 또는 관측)을 실행한다."""

    def __init__(self, devices, store):
        self.devices = devices
        self.store = store
        self._lock = threading.Lock()
        self._thread = None
        self._cancel = threading.Event()
        self.state = self._empty()

    @staticmethod
    def _empty():
        return {"job_id": None, "kind": None, "status": "idle", "step": None, "progress": 0.0,
                "current_target": None, "targets": [], "results": [], "error": None,
                "started_at": None, "finished_at": None}

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def status(self):
        with self._lock:
            return dict(self.state)

    def _set(self, **kw):
        with self._lock:
            self.state.update(kw)

    def cancel(self):
        if not self.running:
            raise DeviceError("실행 중인 작업이 없습니다.")
        self._cancel.set()
        logger.info("[작업] 취소 요청")

    def start(self, kind, targets, exposure=1.0, final_exposure=None, tolerance=None, max_iter=4):
        self.devices.require()
        if self.running:
            raise DeviceError("이미 실행 중인 작업이 있습니다.")
        if not targets:
            raise ValueError("대상이 하나 이상 필요합니다.")
        self._cancel = threading.Event()
        job_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.state = {**self._empty(), "job_id": job_id, "kind": kind, "status": "running",
                      "targets": [t["name"] for t in targets],
                      "started_at": datetime.now().isoformat(timespec="seconds")}
        args = (kind, targets, exposure, final_exposure or exposure * 2, tolerance, max_iter)
        self._thread = threading.Thread(target=self._run, args=args, daemon=True)
        self._thread.start()
        return self.status()

    def _run(self, kind, targets, exposure, final_exposure, tolerance, max_iter):
        pipe = Pipeline(self.devices, self.store, self._cancel)
        label = "자동 관측" if kind == "observation" else "자동 보정"
        logger.info(f"[작업] {label} 시작: {', '.join(t['name'] for t in targets)}")
        n = len(targets)
        try:
            for idx, t in enumerate(targets):
                self._set(current_target=t["name"], progress=idx / n)

                def on_step(step, _idx=idx):
                    self._set(step=step)

                res = correct_to_target(pipe, t["name"], t["ra"], t["dec"], exposure=exposure,
                                        tolerance=tolerance, max_iter=max_iter, on_step=on_step)
                if kind == "observation":
                    on_step("final capture")
                    img, meta = pipe.capture(final_exposure, target=t["name"], purpose="observation")
                    stars, solve = pipe.analyze(img, meta)
                    res["observation_image_id"] = meta["id"]
                    res["observation_stars"] = len(stars)
                    if solve["success"]:
                        res["observation_error_arcsec"] = round(
                            angular_separation_deg(t["ra"], t["dec"], solve["ra"], solve["dec"]) * 3600, 1)
                    logger.info(f"[관측] {t['name']}: 최종 촬영 완료 ({final_exposure}s, 별 {len(stars)}개)")
                with self._lock:
                    self.state["results"] = self.state["results"] + [res]
            self._set(status="done", progress=1.0, step=None)
            logger.info(f"[작업] {label} 완료")
        except Cancelled:
            self._set(status="cancelled", step=None)
            logger.warning(f"[작업] {label} 취소됨")
            try:
                tel, _ = self.devices.require()
                tel.stop()
            except Exception:
                pass
        except Exception as e:
            self._set(status="failed", error=str(e), step=None)
            logger.error(f"[작업] {label} 실패: {e}")
            logger.debug(traceback.format_exc())
        finally:
            self._set(finished_at=datetime.now().isoformat(timespec="seconds"))
