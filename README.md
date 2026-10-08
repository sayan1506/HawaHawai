# HawaHawai

AI-powered School Air-Safety Advisor for the AWS Environmental Hacks hackathon. Pilot: one configurable Delhi-NCR school. Roadmap: [.response/HawaHawai_Project_Phases.md](.response/HawaHawai_Project_Phases.md).

Phase 0 provides React/TypeScript/Vite PWA scaffolding, a Python health backend, Strands provider initialization, API/profile contracts, isolated Docker development, and the deployed `HawaHawaiDev` CDK stack. Environmental integration and school recommendations have not started.

Local frontend: http://127.0.0.1:5173/

Deployed health: https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/health

## Layout

```text
frontend/       React + TypeScript + Vite PWA shell
backend/        Standard-library Lambda and local HTTP adapter; backend-only .env
agent/          Explicit Strands Gemini/Groq adapters; no school tools yet
infra/          TypeScript CDK stack
contracts/      OpenAPI 3.1, school schema, fictional demo profile
scripts/        Contract generation, health tests, isolation/billing checks
.response/      Roadmap, architecture, diff review, checkpoint
.local/         Ignored generated deployment outputs and verification evidence
```

## Local development

Prerequisites: Node >=22.12, Python 3.12, AWS CLI profile `hawahawai`, and running Docker Desktop. CDK is a pinned npm dependency; no global installation or re-bootstrap is needed.

```powershell
npm ci
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.lock.txt
docker info
docker ps -a
docker image ls
docker network ls
docker volume ls
docker compose -p hawahawai-dev build --pull=false backend
docker compose -p hawahawai-dev up -d --no-build --pull never backend
Invoke-RestMethod http://127.0.0.1:18080/health
npm run dev
```

The Dockerfile reuses a verified existing Python image by digest without retagging it. On another machine, explicitly select a compatible Python 3.12 base via `--build-arg PYTHON_BASE=...` if necessary. Never delete existing images or run cleanup/prune commands.

Docker creates `hawahawai-backend:phase0`, `hawahawai-backend-dev`, and `hawahawai-dev-network`; no volumes. Host port 18080 avoids the existing service on 8000. Never stop/restart/delete unrelated Docker resources. The native Python adapter listens on 8000; on this machine use the Docker mapping to avoid the occupied port.

`frontend/.env.local` selects the public deployed backend. To use local Docker, set `VITE_API_BASE_URL=http://127.0.0.1:18080`. API keys belong only in the ignored `backend/.env`; never use a `VITE_` secret variable. Add `GEMINI_API_KEY` or `GROQ_API_KEY` locally when available. Keys are not deployed to Lambda in Phase 0.

## Verification

```powershell
npm run build
.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe scripts/health_smoke.py
.venv\Scripts\python.exe scripts/ai_smoke.py
```

The AI probe exits 2 while the key is empty. Once populated, it makes one harmless Strands connectivity invocation. Groq can be selected with `HAWAHAWAI_AI_PROVIDER=groq`; Bedrock remains disabled. School tool orchestration and automated fallback are Phase 3 work.

## AWS infrastructure

All operations use profile `hawahawai`, region `us-east-1`, account `649437299529`. The CDK entrypoint rejects a different profile/account/region. Run from the repository root:

```powershell
$env:AWS_PROFILE = 'hawahawai'
$env:AWS_REGION = 'us-east-1'
aws sts get-caller-identity --profile hawahawai --region us-east-1
npm run cdk -- synth HawaHawaiDev --profile hawahawai --quiet
python scripts/check_template.py
npm run cdk -- diff HawaHawaiDev --profile hawahawai --no-change-set
# Deploy only after reviewing this named stack's diff.
npm run cdk -- deploy HawaHawaiDev --profile hawahawai --exclusively --require-approval never --outputs-file .local/cdk-outputs.json
```

The stack has a Python 3.12 ARM64 health Lambda, HTTP API, logging-only execution role/policy, and seven-day log group. API throttle: 5 requests/second, burst 10. Lambda: 128 MB, five seconds. These settings are not a spending ceiling. DynamoDB and Amplify belong to later roadmap phases. No budget was created, at the user's request; credit applicability remains unverified because Billing GetCredits returned AccessDenied.

Standard CDK deployment publishes its HawaHawai stack template to the existing bootstrap bucket and uses existing deployment roles. It does not update/redeploy `CDKToolkit`. Never bootstrap, destroy, modify ChugLi, deploy unrelated stacks, or perform Git staging/commits/pushes/remote writes.

`python scripts/isolation_snapshot.py before` captures a non-overwritable baseline. `python scripts/isolation_snapshot.py after` compares Docker definitions, unrelated stack templates/events/resources, ChugLi Lambda configurations, and Git HEAD/reflog/index. Do not overwrite the baseline from this first run. This checks observable definitions; it does not inspect unrelated application data.

## Contracts and current limitations

Only `GET /health` is implemented. All `/v1` routes in `contracts/openapi.json` are explicitly marked unimplemented. The demo school is fictional, with central Delhi coordinates, and must not be presented as a real pilot partner.

Official restrictions and deterministic rules will own the verdict; AI will explain it. India/US/European AQI remain separate. Missing evidence means `DATA_INSUFFICIENT` or `VERIFY_STATUS`, with no invented verdict. The foundation screen makes this limitation visible.

See `.response/Phase_0_Foundation.md` for architecture and contracts, `.response/Phase_0_CDK_Diff_Review.md` for the first diff, and `.response/Phase_0_Checkpoint.md` for verified results and remaining gates. Phase 1 waits until Phase 0 is fully verified.
