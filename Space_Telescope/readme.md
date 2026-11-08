
# Space Telescope

FastAPI와 Docker 기반 가상 천체망원경 제어 및 자동 관측 시스템

## 기술 스택

| 구분 | 기술 |
|---|---|
| Backend | Python 3.12, FastAPI |
| Frontend | HTML, CSS, JavaScript (빌드 없는 단일 페이지, FastAPI가 직접 제공) |
| Environment | Docker, Docker Compose |
| Device Communication | ASCOM Alpaca, alpyca |
| Simulator | 내장 가상 망원경/카메라, Sky Simulator (Alpaca) |
| Computer Vision | OpenCV, NumPy |
| OS | Windows, macOS |

## 개발 로드맵

### 1. 개발 환경 구성
- [x] Docker Desktop 설치
- [x] Dockerfile 및 compose.yaml 작성
- [x] FastAPI, OpenCV, alpyca 설치 (`requirements.txt`)
- [ ] Docker 컨테이너 실행 확인
- [x] Windows 실행 테스트
- [ ] macOS 실행 테스트

### 2. 가상 망원경 환경 구축
- [ ] Sky Simulator 설치
- [x] 가상 망원경 및 카메라 설정 (내장 가상 장비: `app/devices/sim.py`)
- [ ] ASCOM Alpaca 통신 지원 확인 (Sky Simulator 설치 후 검증 필요)
- [x] 가상 망원경 수동 제어 테스트

### 3. 망원경 통신 구현
- [x] Docker와 시뮬레이터 네트워크 연결 설정 (`host.docker.internal`, 실제 연결은 미검증)
- [x] alpyca 기반 장비 연결 (`app/devices/alpaca.py`)
- [x] 망원경 상태 및 좌표 조회
- [x] 망원경 이동 명령 구현

### 4. 망원경 제어 REST API 개발
- [x] `POST /telescope/connect`
- [x] `GET /telescope/position`
- [x] `POST /telescope/move`
- [x] `POST /telescope/stop`
- [x] 예외 처리 및 연결 상태 관리

### 5. 프론트엔드 개발
- [x] 웹 대시보드 화면 구성 (`frontend/`, http://localhost:8000)
- [x] 장비 연결 패널 (가상 장비 / ASCOM Alpaca 선택)
- [x] 망원경 좌표 표시 및 하늘 지도 (클릭으로 좌표 입력)
- [x] 대상 선택·이동·정지 제어
- [x] 촬영 이미지 뷰어 (탐지된 별, 목표 위치 오버레이)
- [x] 분석 결과 표시 (Plate Solving 좌표, 오차)
- [x] 자동 보정 / 자동 관측 실행 및 진행 상태 표시
- [x] 실시간 로그 표시

### 6. 가상 카메라 촬영 구현
- [x] 가상 카메라 연결
- [x] 촬영 및 노출 제어
- [x] FITS / 이미지 데이터 획득
- [x] 이미지 저장 및 조회 API

### 7. 컴퓨터 비전 구현
- [x] OpenCV 이미지 전처리
- [x] 별 탐지 및 중심 좌표 계산
- [x] 별의 이동량 추적
- [x] Plate Solving 기반 천체 좌표 계산

### 8. 자동 위치 보정
- [x] 목표 천체 좌표 설정
- [x] 촬영 이미지 기반 현재 방향 추정
- [x] 목표 좌표와 현재 좌표 오차 계산
- [x] 망원경 자동 위치 보정
- [x] 보정 결과 검증

### 9. 자동 관측 시스템 통합
- [x] 목표 천체 선택
- [x] 망원경 자동 이동
- [x] 이미지 자동 촬영
- [x] 이미지 분석 및 위치 보정
- [x] 관측 상태 및 로그 관리
- [x] 전체 프로세스 통합 테스트 (`tests/`)

## 시스템 아키텍처

```text
Windows / macOS
       |
       v
Docker Container
       |
       v
FastAPI  <------------------ 웹 대시보드 (frontend/)
       |
       +-- 내장 가상 장비 (DEVICE_MODE=sim)
       |
       +-- alpyca ------> ASCOM Alpaca
       |                       |
       |                       v
       |                 Sky Simulator
       |                       |
       |                       v
       |                 가상 망원경 / 카메라
       |                       |
       +<----- 이미지 데이터 ---+
       |
       v
OpenCV
       |
       v
별 탐지 / Plate Solving / 위치 오차 계산
       |
       v
망원경 자동 위치 보정
```

## 프로젝트 구조

```text
Space_Telescope/
├── app/
│   ├── main.py          # FastAPI 라우트
│   ├── config.py        # 환경 변수 설정
│   ├── astro.py         # 좌표 계산 (접평면 투영, 각거리)
│   ├── catalog.py       # 관측 대상 목록, 가상 별 카탈로그
│   ├── vision.py        # 전처리, 별 탐지, 이동량 추적, Plate Solving
│   ├── automation.py    # 자동 위치 보정, 자동 관측 작업
│   ├── storage.py       # FITS / PNG / 메타데이터 저장
│   ├── logs.py          # 관측 로그
│   └── devices/
│       ├── sim.py       # 내장 가상 망원경 / 카메라
│       └── alpaca.py    # ASCOM Alpaca (alpyca)
├── frontend/            # 웹 대시보드 (index.html, app.js, style.css)
├── tests/               # pytest
├── Dockerfile
├── compose.yaml
└── requirements.txt
```

## 개발 환경 실행

Docker:

```bash
docker compose up --build
```

로컬 Python:

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

- 웹 대시보드: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- 테스트: `pytest`

### 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DEVICE_MODE` | `sim` | 연결 기본 모드 (`sim` 또는 `alpaca`) |
| `ALPACA_HOST` / `ALPACA_PORT` | `127.0.0.1` / `32323` | Alpaca 장비 주소 |
| `ALPACA_PIXEL_SCALE` | `4.5` | Alpaca 카메라 픽셀 스케일 (arcsec/px) |
| `SIM_SLEW_RATE_DEG` | `8` | 가상 망원경 이동 속도 (deg/s) |
| `SIM_EXPOSURE_DELAY` | `1` | 노출 시간 대비 실제 대기 비율 (0이면 즉시 촬영) |
| `CORRECTION_TOLERANCE_ARCSEC` | `30` | 자동 보정 허용 오차 |
| `DATA_DIR` | `./data` | 이미지·로그 저장 위치 |

## API 요약

| Method | Path | 설명 |
|---|---|---|
| POST | `/telescope/connect` | 장비 연결 (`{"mode": "sim"}` 또는 `{"mode": "alpaca", "host", "port"}`) |
| POST | `/telescope/disconnect` | 연결 해제 |
| GET | `/telescope/position` | 현재 좌표, 이동/추적 상태 |
| POST | `/telescope/move` | `{"target": "Vega"}` 또는 `{"ra": 18.6, "dec": 38.8}` |
| POST | `/telescope/stop` | 이동 정지 |
| GET | `/targets` | 관측 대상 목록 (현재 위치와의 각거리 포함) |
| POST | `/camera/capture` | 촬영 (`{"exposure": 1.0, "analyze": true}`) |
| GET | `/images`, `/images/{id}` | 이미지 목록 / 메타데이터 |
| GET | `/images/{id}/png`, `/images/{id}/fits` | 미리보기 / FITS 원본 |
| POST | `/vision/analyze/{id}` | 별 탐지 + Plate Solving |
| POST | `/vision/track` | 두 이미지 사이 별 이동량 |
| POST | `/correction/run` | 자동 위치 보정 시작 |
| POST | `/observation/start` | 자동 관측 시작 (`{"targets": ["Vega", "Deneb"]}`) |
| GET | `/observation/status` | 작업 진행 상태, 결과 |
| POST | `/observation/cancel` | 작업 취소 |
| GET | `/logs` | 관측 로그 |

## 동작 방식

- **내장 가상 장비**: 가상 망원경은 실제 장비처럼 마운트 오차(고정 오프셋 0.1~0.25° + 이동마다 약 8" 무작위 오차)를 가진다. 그래서 망원경이 보고하는 좌표와 실제로 향한 방향이 다르고, 촬영 이미지를 분석해야 실제 방향을 알 수 있다.
- **가상 하늘**: 1°×1° 타일 단위로 시드를 고정한 난수로 별을 생성해 항상 같은 별 배치가 나온다. 가상 카메라와 Plate Solving이 같은 카탈로그를 쓴다.
- **Plate Solving**: 보고 좌표 주변의 카탈로그 별을 영상 좌표로 투영하고, 탐지된 별과의 (회전, 평행이동)을 투표 방식으로 찾은 뒤 다시 투영해 정밀하게 맞춘다. 천구의 극 근처에서 생기는 시야 회전도 처리한다.
- **자동 보정**: 이동 → 촬영 → Plate Solving → 목표와의 오차 계산 → 명령 좌표 보정을 허용 오차 이내가 될 때까지 반복한다. 보통 1회 보정으로 약 800" 오차가 30" 이내로 줄어든다.

## 참고

- Sky Simulator는 별도 실행하며, Alpaca 연동 및 이미지 획득 방식은 설치 버전에서 검증한다.
- Alpaca 모드의 Plate Solving은 내장 가상 카탈로그 기준이라, 실제 시뮬레이터 이미지에는 별도의 카탈로그나 solver(예: astrometry.net) 연동이 필요하다.
- Windows와 macOS에서 동일한 Docker 개발 환경을 사용한다.
- 초기 범위는 지상 천체망원경 시뮬레이션이며 우주망원경 궤도·자세제어는 포함하지 않는다.
