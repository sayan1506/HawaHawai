# HawaHawai

AI-powered School Air-Safety Advisor for the AWS Environmental Hacks hackathon. Pilot: one configurable Delhi-NCR school. Roadmap: [.response/HawaHawai_Project_Phases.md](.response/HawaHawai_Project_Phases.md).

Phase 1 adds real Open-Meteo/CAMS modeled current conditions and a dated 48-hour forecast, provenance, conservative freshness checks, bounded retries, DynamoDB caching, and a minimal frontend verification view. Official Indian station observations remain explicitly unavailable. School-safety decisions, GRAP activation and AI explanations are not implemented. Phase 0 health and Strands foundations remain intact.

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

Compose updates only `hawahawai-backend-dev` on `hawahawai-dev-network`. Image tags are versioned without overwriting existing images. The school contracts directory is bind-mounted read-only; there are no new Docker volumes or persistent databases. Host port 18080 avoids the existing service on 8000. Never stop/restart/delete unrelated Docker resources. The native Python adapter listens on 8000; on this machine use the Docker mapping to avoid the occupied port.

`frontend/.env.local` selects the public deployed backend. To use local Docker, set `VITE_API_BASE_URL=http://127.0.0.1:18080`. API keys belong only in the ignored `backend/.env`; never use a `VITE_` secret variable. Keys are not deployed to the environmental Lambda. Open-Meteo needs no key for this non-commercial prototype. CPCB/data.gov.in and OpenAQ adapters deliberately remain unavailable: adding a key alone does not enable an unverified integration.

## Verification

```powershell
npm run build
.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe scripts/health_smoke.py
.venv\Scripts\python.exe scripts/ai_smoke.py
.venv\Scripts\python.exe scripts/environmental_smoke.py
.venv\Scripts\python.exe scripts/audit_phase1.py
```

Gemini backend connectivity through Strands passed on 2026-10-08 after the owner populated the local key. No key was displayed or deployed to AWS. The probe makes a harmless connectivity invocation and exits 2 if its selected provider key is missing. Groq can be selected with `HAWAHAWAI_AI_PROVIDER=groq`; Groq connectivity has not been verified. Bedrock remains disabled. School tool orchestration and automated fallback are Phase 3 work.

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

The same Python 3.12 ARM64 Lambda now serves health, school, air and forecast routes. It has 128 MB memory, a 25-second timeout, its existing seven-day log group, and only GetItem/PutItem/UpdateItem permissions on the new `hawahawai-dev-environment-cache` table. The table is on-demand with TTL cleanup; application freshness does not depend on deletion. API throttle remains 5 requests/second, burst 10. There is no additional Lambda, scheduler, VPC, NAT, queue, Amplify deployment, Bedrock usage or paid provider subscription. These controls are not a spending ceiling.

The project owner monitors AWS credit balance, expiry, and spending. No budget or billing-access change is requested. Credit verification is no longer a Phase 0 or deployment blocker, following the owner's instruction. The last read-only check returned `AccessDeniedException: IAM user access not activated`; credit coverage has not been independently confirmed.

For every deployment, reuse existing HawaHawai resources through updates to the same CDK-managed stack where practical. Review `cdk diff` for replacements and retained resources before deploying. After deployment, verify that superseded HawaHawai resources have not been left orphaned and generating avoidable charges. Any cleanup must target only confirmed obsolete HawaHawai resources. If a replacement would leave retained billable resources, or cleanup would affect persistent data or protected Docker images, flag it before deploying and obtain the necessary direction. Never use global cleanup commands, delete existing images, or remove persistent data to reduce costs.

Standard CDK deployment publishes its HawaHawai stack template to the existing bootstrap bucket and uses existing deployment roles. It does not update/redeploy `CDKToolkit`. Never bootstrap, destroy, modify ChugLi, deploy unrelated stacks, or perform Git staging/commits/pushes/remote writes.

`python scripts/isolation_snapshot.py before --phase phase1` captures a non-overwritable phase-specific baseline. `python scripts/isolation_snapshot.py after --phase phase1` compares protected Docker definitions and all existing images, unrelated stack templates/events/resources, ChugLi Lambda configurations, and Git HEAD/reflog/index. Do not overwrite previous baselines. HawaHawai-owned containers/networks can be updated; protected image tags/digests cannot. This checks observable definitions, not unrelated application data.

## Contracts and current limitations

Implemented endpoints:

- [Health](https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/health)
- [Pilot school](https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/v1/schools/delhi-demo-school)
- [Current environmental evidence](https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/v1/schools/delhi-demo-school/air)
- [48-hour outlook](https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/v1/schools/delhi-demo-school/forecast)

The single source of school configuration is `contracts/demo-school.json`. CDK supplies it to Lambda and the frontend imports its non-secret public profile. Coordinates are validated; arbitrary locations, force-refresh parameters and unknown schools are rejected. The school is fictional, not a real pilot partner.

`observations` stays empty when official station readings cannot be verified. `modeled_current` is explicitly modeled; legacy `pollutants`/`aqi` fields alias it, not official observations. Each value has a source ID, forecast timestamp, units or AQI scale, `source_type=model_forecast`, and `observed_at=null`. Missing pollutants are omitted with warnings, never replaced with zero. `generated_at=null` means the model run time was not supplied. UTC API timestamps are shown as IST in the frontend. US AQI must never be used as Indian AQI or directly compared with GRAP thresholds.

Cache policy: modeled current retrieval 15 minutes, forecast retrieval 1 hour, unavailable-observation metadata 5 minutes; fallback at most 6 hours after retrieval, with current model timestamps unusable after 3 hours and marked stale after 15 minutes. Forecasts must still contain all 48 future hourly points. TTL cleanup is 24 hours, refresh lease 30 seconds, failure cooldown 60–3600 seconds. Provider HTTP uses 2-second connect and 3-second read timeouts, at most two attempts with jittered backoff; 429 is not immediately retried. Cache payload compression is lossless and retains original source timestamps. Local Docker uses process-memory cache; AWS uses DynamoDB.

Official restrictions and deterministic rules will own the verdict; AI will explain it. India/US/European AQI remain separate. Missing evidence means `DATA_INSUFFICIENT` or `VERIFY_STATUS`, with no invented verdict. The foundation screen makes this limitation visible.

See [.response/Phase_1_Architecture.md](.response/Phase_1_Architecture.md) and [.response/Phase_1_Checkpoint.md](.response/Phase_1_Checkpoint.md) for Phase 1 behavior and evidence. Previous Phase 0 foundation/diff/checkpoint documents remain historical and are not deleted. Phase 2 has not started.
