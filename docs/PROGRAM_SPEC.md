# Board Item Optimizer 프로그램 명세서

- 문서 버전: 1.0.0
- 기준 구현일: 2026-08-21
- 구현 언어: Python
- 실행 대상: Windows 데스크톱, Raspberry Pi 4B Raspberry Pi OS Lite 64-bit
- 기본 웹 포트: 5000
- API 계약: `docs/openapi.yaml`

## 1. 목적

게임 보드 스크린샷에서 보드 크기, 셀 상태, 발견 보상, 현재 수동 아이템 수량을 자동으로 인식하고 현재 상태에서 기대 효용이 높은 아이템과 표적을 최대 5개 추천한다.

현재 프로그램은 다음 사용 경로를 제공한다.

1. 브라우저 웹 GUI
2. Tkinter 데스크톱 GUI
3. CLI
4. HTTP JSON API
5. 향후 Discord Bot에서 호출할 수 있는 내부 분석 서비스

## 2. 구현 범위

### 2.1 구현 완료

- 5×5, 10×10, 15×15 보드 모델
- 셀 상태 모델과 남은 보상 조건부 확률
- Boom, Special Boom, Lazer X, Lazer Y 효과 계산
- Gunpowder Barrel, Key 효과 엔진
- 자동 발동 아이템의 추천 후보 제외
- 분석적 기대값 기반 전수 후보 평가
- Monte Carlo 후보 검증
- Top-5 추천
- OpenCV 또는 Pillow/NumPy 기반 이미지 분석
- 보드 크기 자동 인식
- 발견 보상 및 공개 셀 인식
- 하단 4개 아이템 슬롯 수량 OCR
- 웹 보드 오버레이
- Raspberry Pi OS Lite 64-bit용 headless 배포

### 2.2 현재 미구현

- Discord Bot 프로세스
- Discord slash command 등록
- 서버측 PNG 오버레이 생성 API
- API 인증 및 사용자별 사용량 제한
- 보드 상태 영속 저장
- 여러 행동을 연속으로 최적화하는 Beam Search/MCTS
- 게임별 학습 기반 비균등 보상 분포

## 3. 시스템 구성

```text
스크린샷
   │
   ▼
ScreenshotAnalyzer
   ├─ 보드 영역·격자·크기 인식
   ├─ 셀 상태 분류
   └─ 하단 아이템 수량 OCR
   │
   ▼
Board + Inventory
   │
   ├─ Probability Engine
   ├─ Item Effect Engine
   ├─ Exhaustive Optimizer
   └─ Monte Carlo Simulator
   │
   ▼
Top-5 Recommendation
   ├─ Web GUI / Tkinter / CLI
   └─ HTTP API → 향후 Discord Bot
```

## 4. 보드 규칙

| 보드 크기 | 총 셀 수 | 고정 총 보상 수 |
|---|---:|---:|
| 5×5 | 25 | 8 |
| 10×10 | 100 | 32 |
| 15×15 | 225 | 72 |

총 보상 수는 입력받지 않는다. 이미지에서 판별한 보드 크기에 따라 자동 결정한다.

### 4.1 셀 상태

| API 값 | 의미 | 아이템 표적/효과 대상 |
|---|---|---|
| `unknown` | 보상 여부 미확인 | 가능 |
| `reward_found` | 발견된 보상 | 불가능 |
| `no_reward` | 공개됐으나 보상 없음 | 불가능 |

### 4.2 좌표

- 내부 모델과 API 좌표는 0부터 시작한다.
- `x`는 왼쪽에서 오른쪽으로 증가하는 열이다.
- `y`는 위에서 아래로 증가하는 행이다.
- 웹 GUI와 사용자 메시지는 1부터 시작하는 좌표로 변환한다.
- 예: API `(7, 11)`은 사용자 표시 `(8, 12)`이다.

## 5. 아이템 규칙

| 아이템 | 작동 방식 | 효과 | 추천 대상 |
|---|---|---|---|
| Boom | 수동 | 표적 중심 3×3의 미확인 셀 | 포함 |
| Special Boom | 수동 | 표적 중심 3×3, 새 보상 가치 2배 | 포함 |
| Lazer X | 수동 | 표적과 같은 행 전체 | 포함 |
| Lazer Y | 수동 | 표적과 같은 열 전체 | 포함 |
| Gunpowder Barrel | 획득 즉시 자동 | 무작위 미확인 셀 중심 3×3 | 제외 |
| Key | 획득 즉시 자동 | 모든 남은 보상 공개, 보드 종료 | 제외 |

Gunpowder Barrel과 Key의 효과 계산 코드는 시뮬레이션 및 단위 테스트를 위해 유지하지만 사용자 수량 입력과 추천 후보에는 포함하지 않는다.

### 5.1 레이저 후보 중복 제거

- Lazer X는 같은 행에서 x만 이동하면 효과 셀이 동일하다.
- 각 행에서 보드 가로 중앙에 가장 가까운 미확인 셀 하나만 대표 표적으로 사용한다.
- Lazer Y는 같은 열에서 y만 이동하면 효과 셀이 동일하다.
- 각 열에서 보드 세로 중앙에 가장 가까운 미확인 셀 하나만 대표 표적으로 사용한다.
- 서로 다른 행의 Lazer X 또는 서로 다른 열의 Lazer Y는 실제 효과 범위가 다르므로 별도 후보로 유지한다.

## 6. 확률과 점수

남은 모든 미확인 셀은 동일한 보상 확률을 가진다고 가정한다.

```text
P(셀의 보상) = 남은 보상 수 / 미확인 셀 수
```

후보가 `n`개의 미확인 셀에 영향을 주고 전체 미확인 셀이 `N`, 남은 보상이 `R`일 때:

```text
기대 신규 보상 = n × R / N × 아이템 배수
한 개 이상 발견 확률 = 1 - C(N-R, n) / C(N, n)
완료 확률 = C(n, R) / C(N, R)  (n >= R인 경우)
```

### 6.1 목표 함수

| API 값 | 기대 보상 | 탐색 셀 | 완료 확률 |
|---|---:|---:|---:|
| `maximize_expected_rewards` | 1.0 | 0.0 | 0.0 |
| `maximize_explored_cells` | 0.0 | 1.0 | 0.0 |
| `maximize_completion_probability` | 0.0 | 0.0 | 1.0 |
| `balanced` | 0.5 | 0.2 | 0.3 |

점수 계산 전에 기대 보상과 탐색 셀 수를 현재 남은 값 기준으로 0~1 범위로 정규화한다.

## 7. 추천 알고리즘

### 7.1 Analytical

1. 수량이 1개 이상인 수동 아이템만 선택한다.
2. 아이템별 유효 표적을 생성한다.
3. 공개된 셀을 제외한 실제 효과 셀 집합을 계산한다.
4. 기대 보상, 탐색 셀 수, 한 개 이상 발견 확률, 완료 확률을 계산한다.
5. 목표 함수 점수, 기대 보상, 탐색 셀 순으로 내림차순 정렬한다.
   - 3×3 후보의 현재 탐색 셀 수가 같으면, 해당 영역을 밝힌 뒤 최적 Lazer X와 Lazer Y가 탐색할 수 있는 셀 수의 평균이 큰 위치를 우선한다.
   - 따라서 현재 아이템으로 가장 많이 탐색하는 원칙이 다음 레이저 잠재력보다 항상 우선한다.
6. 상위 5개를 반환한다.

### 7.2 Monte Carlo

- 분석적 평가 상위 후보를 먼저 선택한다.
- 남은 보상을 미확인 셀에 균등하게 무작위 배치한다.
- 기본 seed는 42다.
- 웹 기본 반복 수는 1,000회다.
- Raspberry Pi 서비스는 최대 10,000회로 제한한다.
- Monte Carlo 결과는 확률·기대값을 검증하며 후보 기본 점수는 분석적 점수를 사용한다.

## 8. 이미지 분석

### 8.1 처리 단계

1. 이미지를 RGB로 변환한다.
2. OpenCV가 있으면 Canny edge와 contour로 보드 외곽 후보를 찾는다.
3. OpenCV가 없으면 NumPy 색상 분포로 보드 후보를 찾는다.
4. 외곽 프레임의 강한 경계를 이용해 실제 내부 셀 격자로 보정한다.
5. 5, 10, 15개 주기의 격자 경계 점수를 비교해 크기를 판별한다.
6. 셀별 패치를 상태로 분류한다.
7. 하단 4개 슬롯에서 수량 숫자를 읽는다.

### 8.2 셀 분류

- 파랑·보라 고채도 아이콘: `reward_found`
- 노랑 획득 아이콘: `reward_found`
- 어두운 갈색 공개 셀: `no_reward`
- 밝은 석재 타일: `unknown`

### 8.3 아이템 수량 OCR

하단 슬롯 순서는 다음으로 고정한다.

1. Boom
2. Special Boom
3. Lazer X
4. Lazer Y

각 슬롯의 밝은 숫자 픽셀을 연결 성분으로 분리하고 정규화한 뒤 굵은 숫자 폰트 템플릿과 비교한다.

- Windows 폰트: Segoe UI Bold, Arial Bold, Calibri Bold
- Linux/Pi 폰트: DejaVu Sans Bold, Liberation Sans Bold
- Pi 설치 스크립트는 `fonts-dejavu-core`를 설치한다.

### 8.4 이미지 전제조건

- 현재 OCR 슬롯 위치는 `Sample_Board.png`와 같은 게임 UI 비율을 전제로 한다.
- 전체 이미지가 비례 리사이즈된 경우는 지원한다.
- 보드나 하단 아이템 바가 잘린 이미지는 지원하지 않는다.
- 테마, 아이콘, 글꼴이 크게 변경되면 색상 임계값 또는 템플릿 갱신이 필요하다.

## 9. HTTP API

정식 스키마는 `docs/openapi.yaml`을 따른다.

### 9.1 `GET /api/health`

서비스 상태, OpenCV 사용 여부, 서버의 Monte Carlo 최대 반복 수를 반환한다.

### 9.2 `POST /api/analyze`

- Content-Type: `multipart/form-data`
- `image`: PNG/JPEG 파일, 선택 항목
- 이미지가 없으면 서버의 초기 15×15 보드 `Default.png`를 분석한다.
- Raspberry Pi 서비스 업로드 제한은 8MB다.

응답에는 보드 상태, 고정 총 보상 수, 발견/남은 보상, 아이템 수량, 보드 영역, 원본 이미지 data URL이 포함된다.

### 9.3 `POST /api/recommend`

- Content-Type: `application/json`
- `/api/analyze`의 보드와 아이템 수량을 입력으로 사용한다.
- `mode`: `analytical` 또는 `monte_carlo`
- 추천은 가장 좋은 순서로 최대 5개가 반환된다.
- API 응답 좌표는 0부터 시작한다.

### 9.4 오류

| HTTP 상태 | 의미 |
|---:|---|
| 200 | 성공 |
| 400 | 보드 크기, 셀 상태, 입력 값 오류 |
| 413 | 업로드 제한 초과 |
| 500 | 처리되지 않은 서버 오류 |

## 10. 웹 GUI

- PNG/JPG 스크린샷 업로드 또는 샘플 이미지 사용
- 운영체제 캡처 이미지를 페이지 어디에서나 `Ctrl+V`로 붙여넣어 즉시 분석
- 클립보드에서 이미지 항목만 수신하며 일반 텍스트 붙여넣기는 가로채지 않음
- 보드 크기와 보상 수 자동 표시
- 아이템 수량을 읽기 전용 `×수량`으로 표시
- 목표 함수와 평가 방식 선택
- 추천 Top-5 카드
- 원본 이미지 위 효과 범위와 표적 표시
- 반투명 빨간 셀: 아이템 효과 범위
- 굵은 빨간 박스: 실제 추천 표적

### 10.1 보드 크기 색상 아이템 보정

격자 경계 주기성으로 5×5, 10×10, 15×15 후보 점수를 계산한 뒤 각 후보 크기로 보드를 임시 분할하여 색상 보상·아이템이 포함된 셀 수를 센다.

- 5×5 후보에서 색상 아이템 셀이 9개를 초과하면 5×5 후보를 제외한다.
- 10×10 후보에서 색상 아이템 셀이 36개를 초과하면 10×10 후보를 제외한다.
- 실제 고정 보상 수는 각각 8개와 32개지만, 프레임 오차로 아이콘 하나가 인접 셀에 걸리는 상황을 고려해 1칸과 4칸의 여유를 둔다.
- 15×15는 현재 지원하는 최대 크기이므로 최종 폴백 후보로 항상 유지한다.

이 보정은 색상 아이템이 적은 초반에는 기존 격자선 판별을 유지하고, 아이템이 많이 드러난 후반에는 작은 보드로 축소 인식되는 것을 방지한다.

추가로 색상 아이콘 픽셀의 2차원 배치 주기를 사용한다. 각 픽셀에서 5×5, 10×10, 15×15 후보 셀 중심까지의 정규화 거리를 계산하며 평균 거리가 작을수록 해당 격자에 잘 정렬된 것으로 본다.

- 색상 픽셀이 보드 가로·세로의 각각 30% 이상 범위에 분포해야 배치 신호를 사용한다.
- 한 후보의 중심 정렬 오차가 충분히 작고 다른 후보보다 명확하게 낮을 때만 격자선 점수를 보정한다.
- 아이콘이 적거나 여러 격자 크기에 동시에 들어맞는 경우에는 배치만으로 크기를 확정하지 않는다.
- 복수 후보가 비슷하게 정렬되면 프레임 경계와 격자선 주기성 결과를 우선하고, 조건을 만족하는 최대 후보 크기를 선택한다.

## 11. Raspberry Pi OS Lite 64-bit 배포

### 11.1 런타임

- `opencv-python-headless`
- Flask
- Gunicorn 1 worker, 2 threads
- systemd 자동 실행
- 포트 5000, LAN 인터페이스 바인딩
- 업로드 최대 8MB
- Monte Carlo 최대 10,000회

### 11.2 설치

```bash
cd ~/travel
bash scripts/install_raspberry_pi_lite.sh
```

### 11.3 관리

```bash
sudo systemctl status board-item-optimizer
journalctl -u board-item-optimizer -f
sudo systemctl restart board-item-optimizer
```

## 12. Discord Bot 연동 명세

### 12.1 권장 배치

Discord Bot과 분석 서버를 같은 Raspberry Pi에서 실행하고 Bot이 `http://127.0.0.1:5000`으로 호출한다. 이 구성에서는 분석 API를 인터넷에 직접 공개할 필요가 없다.

```text
Discord 사용자
   │ 첨부 이미지 + slash command
   ▼
Discord Bot
   │ localhost HTTP
   ▼
Board Item Optimizer API
```

### 12.2 제안 명령

```text
/board-optimize image:<attachment>
                objective:<balanced|reward|explore|completion>
                mode:<analytical|monte_carlo>
                iterations:<optional>
```

기본값:

- objective: `balanced`
- mode: `analytical`
- iterations: 1,000

### 12.3 Bot 처리 흐름

1. 첨부 파일 MIME이 PNG 또는 JPEG인지 확인한다.
2. 파일 크기가 8MB 이하인지 확인한다.
3. Discord 응답을 지연 처리 상태로 전환한다.
4. 이미지를 `POST /api/analyze`에 multipart로 전달한다.
5. 응답의 `board` 필드와 `inventory`를 `POST /api/recommend`에 전달한다.
6. 추천이 없으면 현재 사용 가능한 수동 아이템이 없다고 응답한다.
7. 추천이 있으면 1위 아이템, 사용자 좌표, 기대 보상, 탐색 셀, 발견 확률을 표시한다.
8. 필요하면 2~5위는 Discord embed의 추가 필드로 표시한다.

### 12.4 권장 Discord 응답 예

```text
추천 #1: Lazer X
표적: (8, 12)
신규 탐색: 14칸
기대 보상: 4.67
보상 1개 이상: 99.76%
완료 확률: 0.00%

현재 아이템: Boom ×1 · Special Boom ×0 · Lazer X ×2 · Lazer Y ×1
보드: 15×15 · 발견 23/72
```

### 12.5 Discord 연동 시 추가 권장 API

다음 항목은 아직 구현되지 않았으며 Bot 구현 단계에서 추가하는 것이 좋다.

#### `POST /api/optimize`

이미지 업로드 한 번으로 분석과 추천을 함께 수행한다. 현재의 두 API 호출을 하나로 줄인다.

#### `POST /api/overlay`

추천 표적과 효과 범위를 그린 PNG를 반환한다. 현재 오버레이는 브라우저 Canvas에서만 생성되므로 Discord 첨부에는 직접 사용할 수 없다.

#### `include_image=false`

Bot은 원본 data URL이 필요하지 않은 경우가 많다. 분석 응답에서 큰 base64 필드를 제외하는 옵션을 추가하면 메모리와 전송량을 줄일 수 있다.

### 12.6 보안

현재 API에는 인증이 없다.

- Bot과 API가 같은 Pi에 있으면 API는 localhost로만 별도 실행하는 구성을 권장한다.
- LAN 또는 인터넷에 공개해야 하면 API token, TLS reverse proxy, 요청 제한을 추가한다.
- Discord Bot token은 소스에 저장하지 않고 환경변수 또는 systemd EnvironmentFile로 제공한다.
- 사용자 첨부 파일은 디스크에 영구 저장하지 않는다.

## 13. 데이터 영속성과 동시성

- 현재 서버는 무상태(stateless)다.
- 분석 결과와 사용자 이미지를 데이터베이스에 저장하지 않는다.
- 브라우저 또는 Bot이 분석 응답을 다음 추천 요청에 그대로 전달한다.
- Raspberry Pi 배포는 메모리 사용량을 줄이기 위해 Gunicorn worker 1개를 사용한다.
- Monte Carlo 요청은 CPU를 오래 점유할 수 있으므로 Discord Bot에서는 동시 요청 큐 또는 사용자별 rate limit을 권장한다.

## 14. 환경 변수

| 이름 | 기본값 | Pi 서비스 값 | 의미 |
|---|---:|---:|---|
| `BOARD_OPTIMIZER_MAX_UPLOAD_BYTES` | 8,388,608 | 8,388,608 | 업로드 제한 |
| `BOARD_OPTIMIZER_MAX_MC_ITERATIONS` | 100,000 | 10,000 | Monte Carlo 최대 반복 수 |
| `PYTHONUNBUFFERED` | 미설정 | 1 | systemd 로그 즉시 출력 |

## 15. 테스트 기준

현재 자동 테스트는 다음을 검증한다.

- 지원 보드 크기와 고정 보상 수
- 공개 셀과 남은 보상 업데이트
- Boom과 레이저 효과
- Key 효과 엔진
- 확률 계산
- 추천 정렬
- 레이저 축 중복 제거
- 자동 발동 아이템 추천 제외
- 샘플 보상 23개 인식
- 샘플 아이템 수량 `0,0,0,0` 인식
- 5/10/15 격자 주기 판별
- 웹 health/analyze/recommend 흐름

## 16. 향후 변경 시 호환성 규칙

- API 필드를 제거하거나 타입을 변경할 때는 API 버전을 올린다.
- 새 필드는 기존 클라이언트가 무시할 수 있도록 선택 필드로 추가한다.
- 셀 상태 문자열은 `unknown`, `reward_found`, `no_reward`를 유지한다.
- API 좌표는 계속 0-based로 유지하고 사용자 계층에서만 1-based로 변환한다.
- 아이템 슬롯 순서가 게임 UI에서 변경되면 OCR 매핑과 이 문서를 함께 갱신한다.
- Discord Bot은 `docs/openapi.yaml`을 기준으로 클라이언트를 구현한다.
