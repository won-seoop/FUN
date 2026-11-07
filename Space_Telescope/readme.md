
# Space Telescope

FastAPI와 Docker 기반 가상 천체망원경 제어 및 자동 관측 시스템

## 기술 스택

| 구분 | 기술 |
|---|---|
| Backend | Python 3.12, FastAPI |
| Environment | Docker, Docker Compose |
| Device Communication | ASCOM Alpaca, alpyca |
| Simulator | Sky Simulator |
| Computer Vision | OpenCV, NumPy |
| OS | Windows, macOS |

## 개발 로드맵

### 1. 개발 환경 구성
- [ ] Docker Desktop 설치
- [ ] Dockerfile 및 compose.yaml 작성
- [ ] FastAPI, OpenCV, alpyca 설치
- [ ] Docker 컨테이너 실행 확인
- [ ] Windows / macOS 실행 테스트

### 2. 가상 망원경 환경 구축
- [ ] Sky Simulator 설치
- [ ] 가상 망원경 및 카메라 설정
- [ ] ASCOM Alpaca 통신 지원 확인
- [ ] 가상 망원경 수동 제어 테스트

### 3. 망원경 통신 구현
- [ ] Docker와 시뮬레이터 네트워크 연결
- [ ] alpyca 기반 장비 연결
- [ ] 망원경 상태 및 좌표 조회
- [ ] 망원경 이동 명령 구현

### 4. 망원경 제어 REST API 개발
- [ ] `POST /telescope/connect`
- [ ] `GET /telescope/position`
- [ ] `POST /telescope/move`
- [ ] `POST /telescope/stop`
- [ ] 예외 처리 및 연결 상태 관리

### 5. 가상 카메라 촬영 구현
- [ ] 가상 카메라 연결
- [ ] 촬영 및 노출 제어
- [ ] FITS / 이미지 데이터 획득
- [ ] 이미지 저장 및 조회 API

### 6. 컴퓨터 비전 구현
- [ ] OpenCV 이미지 전처리
- [ ] 별 탐지 및 중심 좌표 계산
- [ ] 별의 이동량 추적
- [ ] Plate Solving 기반 천체 좌표 계산

### 7. 자동 위치 보정
- [ ] 목표 천체 좌표 설정
- [ ] 촬영 이미지 기반 현재 방향 추정
- [ ] 목표 좌표와 현재 좌표 오차 계산
- [ ] 망원경 자동 위치 보정
- [ ] 보정 결과 검증

### 8. 자동 관측 시스템 통합
- [ ] 목표 천체 선택
- [ ] 망원경 자동 이동
- [ ] 이미지 자동 촬영
- [ ] 이미지 분석 및 위치 보정
- [ ] 관측 상태 및 로그 관리
- [ ] 전체 프로세스 통합 테스트

## 시스템 아키텍처

```text
Windows / macOS
       |
       v
Docker Container
       |
       v
FastAPI
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
별 탐지 / 위치 오차 계산
       |
       v
망원경 자동 위치 보정
```

## 개발 환경 실행

```bash
docker compose up --build
```

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs

## 참고

- Sky Simulator는 별도 실행하며, Alpaca 연동 및 이미지 획득 방식은 설치 버전에서 검증한다.
- Windows와 macOS에서 동일한 Docker 개발 환경을 사용한다.
- 초기 범위는 지상 천체망원경 시뮬레이션이며 우주망원경 궤도·자세제어는 포함하지 않는다.
