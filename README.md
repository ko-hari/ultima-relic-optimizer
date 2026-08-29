# Board Item Optimizer

보드 스크린샷을 분석하고, 현재 아이템으로 기대 보상과 탐색량을 최대화하는 표적을 추천하는 Python 프로그램입니다.

## 프로그램 명세

- [구현 및 Discord Bot 연동 명세](docs/PROGRAM_SPEC.md)
- [OpenAPI 3.1 API 계약](docs/openapi.yaml)

## 실행

```powershell
python main.py
```

기본 실행은 `Default.png`를 열어 GUI를 표시합니다. 콘솔에서 결과만 보려면:

```powershell
python main.py --no-gui
python main.py --no-gui --monte-carlo 10000 --inventory "Boom=1,Special Boom=1,Lazer X=1,Lazer Y=1"
```

OpenCV가 설치된 Conda 환경에서는 다음처럼 실행하면 Canny/contour 기반 보드 영역 검출을 사용합니다.

```powershell
conda activate travel
python -m pip install -r requirements.txt
python main.py
```

## 웹 GUI

```powershell
conda activate travel
python -m pip install -r requirements.txt
python web_app.py
```

브라우저에서 `http://127.0.0.1:5000`을 엽니다. 웹 GUI는 이미지 업로드, 클립보드 캡처 이미지 `Ctrl+V` 붙여넣기, 샘플 보드 분석, 아이템 수량/목표 함수 설정, 정확 기대값 또는 Monte Carlo 계산, Top-5 추천과 원본 이미지 오버레이를 제공합니다.

보드 크기는 스크린샷 격자에서 자동 판별하며 총 보상 수는 5×5=8, 10×10=32, 15×15=72로 고정됩니다. 하단 네 아이템 슬롯의 `×수량`을 자동 인식하므로 보상 수와 아이템 수량을 별도로 입력하지 않습니다.

`Gunpowder Barrel`과 `Key`는 획득 즉시 자동 발동하므로 수량 입력과 추천 후보에서 제외됩니다. `Lazer X`는 행마다, `Lazer Y`는 열마다 동일 효과 후보를 하나로 묶어 중복 추천하지 않습니다.

좌표는 사람이 읽기 쉽게 1부터 표시되며, 내부 모델은 0부터 시작합니다. 샘플 이미지 분석은 Pillow/NumPy만 사용해 15×15 영역을 찾고, 석재/갈색/보라·파랑 아이콘을 각각 미확인/빈 칸/발견 보상으로 분류합니다.

## 테스트

```powershell
pytest -q
```

핵심 계산은 조건부 균등 보상 분포의 정확한 초등적 기대값을 사용합니다. `--monte-carlo N`을 주면 분석 후보를 N회 몬테카를로 시뮬레이션으로 검증합니다.

## Raspberry Pi 4B · Raspberry Pi OS Lite 64-bit

Lite 환경에서는 Tkinter 데스크톱 GUI를 설치하지 않고 웹 GUI만 실행합니다. 프로젝트를 공백이 없는 경로에 복사한 후 다음 설치 스크립트를 실행합니다.

```bash
cd ~/travel
bash scripts/install_raspberry_pi_lite.sh
```

설치 스크립트는 다음 작업을 수행합니다.

- ARM64용 `opencv-python-headless`와 Gunicorn 설치
- DejaVu Bold 폰트를 설치해 하단 아이템 수량 OCR에 사용
- `.venv` 가상환경 생성
- 부팅 시 자동 실행되는 `board-item-optimizer.service` 등록
- 모든 LAN 인터페이스의 포트 5000에서 웹 서버 실행
- 업로드 이미지 8MB, Monte Carlo 최대 10,000회로 제한

다른 기기에서 `http://라즈베리파이_IP:5000`으로 접속합니다.

```bash
sudo systemctl status board-item-optimizer
journalctl -u board-item-optimizer -f
sudo systemctl restart board-item-optimizer
```
