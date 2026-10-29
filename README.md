# MCCBA API

수학 think-aloud 전사, 회고 인터뷰, LangGraph 기반 문항별 진단, Firestore·Cloud Storage 저장을 담당하는 FastAPI 백엔드다.

## 구조

- `app/main.py`: HTTP API와 세션 단계 검증
- `app/agents`: LangGraph, 실제 모델 에이전트, 키 없는 데모 에이전트
- `app/repositories`: 로컬 JSON과 Firestore 저장소
- `app/services`: 녹음 파일 전사
- `resources`: 문제 스키마와 RAG 문항
- `tests`: 에이전트·API 통합 테스트

## 로컬 실행

Python 3.12를 기준으로 한다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- 상태 확인: `http://localhost:8000/health`
- API 문서: `http://localhost:8000/docs`

기본값은 `DATA_BACKEND=json`, `LLM_PROVIDER=mock`이므로 외부 계정 없이 전체 흐름을 시험할 수 있다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 컨테이너 확인

Docker가 설치되어 있다면 다음과 같이 확인한다.

```powershell
docker build -t mccba-api .
docker run --rm -p 8080:8080 --env-file .env mccba-api
```

## Cloud Run 준비

1. `cloud-run.env.example.yaml`을 `cloud-run.env.yaml`로 복사하고 Netlify 주소와 모델명을 수정한다.
2. `OPENAI_API_KEY`는 파일에 쓰지 말고 Secret Manager에 저장한다.
3. Cloud Run 서비스 계정에 필요한 Firestore, Storage, Secret Manager 최소 권한을 부여한다.
4. 소스에서 배포한다.

```powershell
gcloud config set project project-hail-mary-51762
gcloud run deploy mccba-api `
  --source . `
  --region asia-northeast3 `
  --service-account YOUR_SERVICE_ACCOUNT `
  --env-vars-file cloud-run.env.yaml `
  --set-secrets OPENAI_API_KEY=OPENAI_API_KEY:1
```

Cloud Run URL이 발급되면 Netlify에 다음 값을 설정한다.

```text
NEXT_PUBLIC_API_BASE=https://YOUR_CLOUD_RUN_URL/api
```

## 공개 배포 전 보안 주의

현재 저장소는 기술 흐름을 검증하는 MVP다. 학생 대상 공개 운영 전에는 Firebase ID 토큰 검증, 학생 세션 소유권 확인, 연구자 API 역할 제한을 추가해야 한다. 이 보호가 추가되기 전에는 Cloud Run 서비스를 공개 인터넷에 노출하지 않는다.

운영에서는 `DATA_BACKEND=firestore`와 `AUDIO_BUCKET`을 반드시 설정한다. Cloud Run 로컬 파일 시스템은 영구 저장소가 아니므로 `json` 저장과 로컬 음성 저장은 개발 전용이다.

