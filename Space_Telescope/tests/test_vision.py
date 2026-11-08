import math

import numpy as np
import pytest

from app import vision
from app.astro import angular_separation_deg, deproject, offset_position, project
from app.devices.sim import render_starfield
from app.storage import read_fits, write_fits


def test_projection_roundtrip():
    xi, eta = project(10.3 * 15, 20.2, 10 * 15, 20)
    ra, dec = deproject(float(xi), float(eta), 10 * 15, 20)
    assert ra == pytest.approx(10.3 * 15, abs=1e-9)
    assert dec == pytest.approx(20.2, abs=1e-9)


def test_detect_stars_finds_sources():
    img = render_starfield(5.0, 10.0, 800, 600, 4.5, 1.0, np.random.default_rng(0))
    stars = vision.detect_stars(img)
    assert len(stars) >= 10
    assert all(0 <= s["x"] < 800 and 0 <= s["y"] < 600 for s in stars)


def test_track_shift_recovers_known_offset():
    rng = np.random.default_rng(1)
    a = render_starfield(5.0, 10.0, 800, 600, 4.5, 1.0, rng)
    ra2, dec2 = offset_position(5.0, 10.0, -20 * 4.5 / 3600, 0)  # 20px 이동
    b = render_starfield(ra2, dec2, 800, 600, 4.5, 1.0, rng)
    r = vision.track_shift(a, b)
    assert abs(abs(r["dx"]) - 20) < 1.0
    assert abs(r["dy"]) < 1.0


@pytest.mark.parametrize("ra,dec", [(6.75, -16.7), (18.6, 38.8), (2.53, 89.26), (3.0, -89.6), (23.99, 0.0)])
@pytest.mark.parametrize("angle", [0, 120, 240])
def test_plate_solve_with_pointing_error(ra, dec, angle):
    off = 0.2
    true_ra, true_dec = offset_position(ra, dec, off * math.cos(math.radians(angle)),
                                        off * math.sin(math.radians(angle)))
    img = render_starfield(true_ra, true_dec, 800, 600, 4.5, 1.0, np.random.default_rng(angle))
    stars = vision.detect_stars(img)
    r = vision.plate_solve(stars, ra, dec, 800, 600, 4.5)
    assert r["success"], r
    assert angular_separation_deg(true_ra, true_dec, r["ra"], r["dec"]) * 3600 < 5


def test_fits_roundtrip(tmp_path):
    img = (np.random.default_rng(2).random((60, 80)) * 65535).astype(np.uint16)
    p = tmp_path / "x.fits"
    write_fits(p, img, [("EXPTIME", 1.5, "s"), ("OBJECT", "Vega", "")])
    assert p.stat().st_size % 2880 == 0
    assert np.array_equal(read_fits(p), img)
