# HawaHawai

AI-powered School Air-Safety Advisor for the AWS Environmental Hacks hackathon. Pilot: one configurable Delhi-NCR school. Roadmap: [.response/HawaHawai_Project_Phases.md](.response/HawaHawai_Project_Phases.md).

Phases 0-2 remain operational. Phase 3 adds real Strands tool orchestration, constrained English/Hindi explanations, Gemini primary, configured Groq failover, and an explicit deterministic fallback. See the [Phase 3 checkpoint](.response/Phase_3_Checkpoint.md) for final verification status. Official station observations remain unavailable and current GRAP activation is **UNKNOWN**: documentary research is not a recorded human verification. Modeled US AQI never establishes an official stage. The `school-safety-v1` engine remains the only safety authority.

Local frontend: http://127.0.0.1:5173/

Deployed health: https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/health

## Layout

```text
frontend/       React + TypeScript + Vite PWA shell
backend/        Lambda/local adapter, environmental/safety/advisory services; private .env
agent/          Strands trusted tools, approved bilingual language, provider adapters
infra/          TypeScript CDK stack
contracts/      OpenAPI 3.1, school schema, fictional demo profile
scripts/        Contracts, smoke tests, controlled registry publication, isolation audits
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
# Before any build, select a NEW hawahawai- image tag in compose.yaml.
# Refuse to build if that tag already exists; existing images must not be overwritten.
docker compose -p hawahawai-dev build --pull=false backend
docker compose -p hawahawai-dev up -d --no-build --pull never backend
Invoke-RestMethod http://127.0.0.1:18080/health
npm run dev
```

The Dockerfile reuses a verified existing Python image by digest without retagging it. On another machine, explicitly select a compatible Python 3.12 base via `--build-arg PYTHON_BASE=...` if necessary. Never delete existing images or run cleanup/prune commands.

Compose updates only `hawahawai-backend-dev` on `hawahawai-dev-network`. Image tags are versioned without overwriting existing images. The school contracts directory is bind-mounted read-only; there are no new Docker volumes or persistent databases. Host port 18080 avoids the existing service on 8000. Never stop/restart/delete unrelated Docker resources. The native Python adapter listens on 8000; on this machine use the Docker mapping to avoid the occupied port.

`frontend/.env.local` selects the public deployed backend. To use local Docker, set `VITE_API_BASE_URL=http://127.0.0.1:18080`. API keys belong only in ignored `backend/.env`; never use a `VITE_` secret variable. Lambda loads keys from its single CDK-owned Secrets Manager secret, not environment values or code assets. Docker intentionally has no keys and verifies deterministic fallback. Open-Meteo needs no key for this non-commercial prototype. CPCB/data.gov.in and OpenAQ remain unavailable; keys alone do not enable unverified integrations.

## Verification

```powershell
npm run build
.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
node --import tsx --test frontend/tests/*.test.mjs
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe scripts/health_smoke.py
.venv\Scripts\python.exe scripts/environmental_smoke.py
.venv\Scripts\python.exe scripts/safety_smoke.py
.venv\Scripts\python.exe scripts/safety_smoke.py --local
.venv\Scripts\python.exe scripts/advisory_smoke.py
.venv\Scripts\python.exe scripts/advisory_smoke.py --base http://127.0.0.1:18080
.venv\Scripts\python.exe scripts/advisory_api_checks.py
.venv\Scripts\python.exe scripts/audit_phase3.py
```

Gemini's actual Strands explanation smoke passed on 2026-10-08 using real deployed school evidence. `scripts/advisory_smoke.py --local-provider` makes one bounded Gemini call using ignored local configuration. Groq failure handling is mock-tested; no Groq key is currently configured, so live Groq access remains unverified. Model access is account-specific; configure `HAWAHAWAI_GROQ_MODEL` with an available tool/JSON-capable model when adding a key. Bedrock is explicitly disabled, never selected implicitly.

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

The same Python 3.12 ARM64 Lambda serves the six existing GET routes plus GET/POST advisory routes. It uses 512 MB memory, a 25-second timeout and the existing seven-day log group. The existing on-demand `hawahawai-dev-environment-cache` table also stores regulatory history and explanation plans. Lambda can read that table, but PutItem/UpdateItem are restricted to the configured school's key prefix; it cannot update regulatory keys. No DeleteItem, Scan, transaction or administrative permission is granted to Lambda. A new `hawahawai-dev-ai-credentials` secret grants only exact-resource GetSecretValue to this Lambda. Environmental TTL cleanup is separate from application freshness; registry records have no TTL. API throttle remains 5 requests/second, burst 10. There is no additional Lambda, table, scheduler, VPC, NAT, queue, Amplify deployment, Bedrock usage or paid provider subscription. Secrets Manager and Lambda have normal usage charges; these controls are not a spending ceiling.

The project owner monitors AWS credit balance, expiry, and spending. No budget or billing-access change is requested. Credit verification is no longer a Phase 0 or deployment blocker, following the owner's instruction. The last read-only check returned `AccessDeniedException: IAM user access not activated`; credit coverage has not been independently confirmed.

For every deployment, reuse existing HawaHawai resources through updates to the same CDK-managed stack where practical. Review `cdk diff` for replacements and retained resources before deploying. After deployment, verify that superseded HawaHawai resources have not been left orphaned and generating avoidable charges. Any cleanup must target only confirmed obsolete HawaHawai resources. If a replacement would leave retained billable resources, or cleanup would affect persistent data or protected Docker images, flag it before deploying and obtain the necessary direction. Never use global cleanup commands, delete existing images, or remove persistent data to reduce costs.

Standard CDK deployment publishes its HawaHawai stack template to the existing bootstrap bucket and uses existing deployment roles. It does not update/redeploy `CDKToolkit`. Never bootstrap, destroy, modify ChugLi, deploy unrelated stacks, or perform Git staging/commits/pushes/remote writes.

`python scripts/isolation_snapshot.py before --phase phase3` captures a non-overwritable phase-specific baseline. `python scripts/isolation_snapshot.py after --phase phase3` compares protected Docker definitions and all existing images, unrelated stack templates/events/resources, ChugLi Lambda configurations, and Git HEAD/reflog/index. Do not overwrite previous baselines. HawaHawai-owned containers/networks can be updated; protected image tags/digests cannot. This checks observable definitions, not unrelated application data.

## Contracts and current limitations

Implemented endpoints:

- [Health](https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/health)
- [Pilot school](https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/v1/schools/delhi-demo-school)
- [Current environmental evidence](https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/v1/schools/delhi-demo-school/air)
- [48-hour outlook](https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/v1/schools/delhi-demo-school/forecast)
- [GRAP verification state](https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/v1/schools/delhi-demo-school/grap)
- [Deterministic school recommendation](https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/v1/schools/delhi-demo-school/verdict)
- [English/Hindi explanation (GET; POST also supported)](https://pu8l3a213j.execute-api.us-east-1.amazonaws.com/v1/schools/delhi-demo-school/advisory)

The single source of school configuration is `contracts/demo-school.json`. CDK supplies it to Lambda and the frontend imports its non-secret public profile. Coordinates are validated; arbitrary locations, force-refresh parameters and unknown schools are rejected. The school is fictional, not a real pilot partner.

`observations` stays empty when official station readings cannot be verified. `modeled_current` is explicitly modeled; legacy `pollutants`/`aqi` fields alias it, not official observations. Each value has a source ID, forecast timestamp, units or AQI scale, `source_type=model_forecast`, and `observed_at=null`. Missing pollutants are omitted with warnings, never replaced with zero. `generated_at=null` means the model run time was not supplied. UTC API timestamps are shown as IST in the frontend. US AQI must never be used as Indian AQI or directly compared with GRAP thresholds.

Cache policy: modeled current retrieval 15 minutes, forecast retrieval 1 hour, unavailable-observation metadata 5 minutes; fallback at most 6 hours after retrieval, with current model timestamps unusable after 3 hours and marked stale after 15 minutes. Forecasts must still contain all 48 future hourly points. TTL cleanup is 24 hours, refresh lease 30 seconds, failure cooldown 60–3600 seconds. Provider HTTP uses 2-second connect and 3-second read timeouts, at most two attempts with jittered backoff; 429 is not immediately retried. Cache payload compression is lossless and retains original source timestamps. Local Docker uses process-memory cache; AWS uses DynamoDB.

## Deterministic school policy and regulatory review

`school-safety-v1` supports `GO_OUTDOORS`, `MODIFIED_OUTDOORS`, `INDOOR_ONLY` and `DATA_INSUFFICIENT`. The canonical field is `decision`; compatibility field `verdict` stays null for insufficient evidence. Responses include evaluation time, rule trace, source references, data quality, actions and a short recheck deadline. `?grade=5&activity=sports` is supported; grades 0-12 and documented activity names are validated. Anonymous regulatory writes and stage/verdict override parameters are rejected.

Priority: reviewed mandatory school requirements, applicable regulatory guidance, validated exposure concerns, near-term forecast risk, freshness and uncertainty. US EPA/AirNow guidance supplies **project-adopted health precautions**, not Indian legal thresholds: above 100 modify outdoor exposure; above 150 use indoor alternatives for vigorous sports/PE; above 200 use indoor alternatives for all outdoor activities. These use validated US AQI only and the next three dated forecast hours. Missing observations do not prevent a restrictive model-based precaution. Model-only low pollution, unknown regulation or an incomplete fresh outlook cannot justify `GO_OUTDOORS`. Positive advice additionally requires fresh, identified, co-located physical station evidence; it is never a guarantee of safe air. Raw PM concentrations are not converted into AQI. Indoor-only does not automatically close a school or establish clean indoor air.

The adopted schedule is `grap-2026-09-29`, researched from CAQM's original revised schedule and Direction 104. Its hash-bound school-clause catalog preserves exact hybrid-class grade groups and the distinction between mandatory operations and citizen advice. It cannot activate itself. The public registry is `research-2026-10-08-v2`, with no events, restrictions or human attestation. It truthfully returns `UNKNOWN` / `VERIFY_STATUS`. The first research version remains immutable audit history.

An actual human must review the original current schedule, complete subsequent invocation/revocation history and applicable Delhi school notices before publishing verified status. The controlled local publisher checks reviewed PDF hashes, explicit operator/attestation, jurisdiction, event consistency and verification expiry (at most 24 hours). It atomically writes an immutable version and a compare-and-swap current pointer in the same HawaHawai table. No public update endpoint exists. See [Phase 2 architecture](.response/Phase_2_Architecture.md) for the exact administrative workflow. Previewing the packaged UNKNOWN snapshot is safe and makes no AWS writes:

```powershell
.venv\Scripts\python.exe scripts/publish_regulatory_snapshot.py --research-only
```

Every request reevaluates current inputs; there is no indefinite verdict cache. Registry verification expiry is not legal revocation, and stale data is never made fresh by DynamoDB TTL or a cache read. The Phase 3 agent explains these outputs without overriding them.

See [Phase 3 checkpoint](.response/Phase_3_Checkpoint.md) and [architecture](.response/Phase_3_Architecture.md) for current verification. Earlier [Phase 2 checkpoint](.response/Phase_2_Checkpoint.md), [architecture](.response/Phase_2_Architecture.md), [Phase 1 architecture](.response/Phase_1_Architecture.md) and [checkpoint](.response/Phase_1_Checkpoint.md) remain historical evidence. No staging, commits or pushes are performed by this workflow.

## Phase 3 advisory

`GET /v1/schools/delhi-demo-school/advisory` returns both languages. `POST` accepts the existing `{verdict_id, languages}` contract; a stale verdict returns 409. Grade/activity parameters reuse Phase 2 validation. No arbitrary prompts or public administrative operations are accepted.

The actual Strands agent invokes four trusted, snapshot-pinned tools, then generates a strict JSON plan ordering approved bilingual statements. It does **not** write unrestricted safety prose or translate legal orders independently. All required statements must be present exactly once. Invalid assertions, unknown fields, altered actions, invented URLs, incomplete output or missing uncertainty cause deterministic fallback. Backend-owned verdict, actions, sources, units, freshness and timestamps are attached after generation and Phase 2 is reevaluated. The frontend hides expired explanations and requests data only on explicit user action.

Explanation caching uses the existing table and binds the plan to the authoritative decision fingerprint, policy/language version, regulatory snapshot/state, actions, quality, warnings and source metadata. AI plans expire at the earlier input-validity deadline or five minutes; fallback entries last at most 60 seconds. A school-wide 30-second provider lease limits variant-driven calls. Gemini gets at most eight seconds including SDK setup; Groq gets at most four within a ten-second total budget, reduced to reserve Lambda response time. SDK/provider retries are disabled, maximum one generation per provider. Gemini requires an HTTP deadline of at least ten seconds; application cancellation imposes the shorter actual bound. Cold-start fallback is transparent, not a fabricated AI success.

The only new service is one backend credential secret. It has normal Secrets Manager charges; credits do not imply zero cost. No Bedrock, NAT, queue, scheduler, table, duplicate Lambda or budget is added. The existing function is updated in place; its CPU allocation is 512 MB after measured 256 MB cold-start timeouts.

Before synthesis on a new checkout, prepare Linux ARM64 dependencies (Windows dependency resolution is not suitable because it selects Windows-only markers):

```powershell
docker run --rm --name hawahawai-runtime-packager --cpus 1 --memory 768m --mount "type=bind,source=C:\path\to\HawaHawai,target=/workspace" -w /workspace python@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f python -m pip install --target .local/phase3-dependencies-aarch64 --platform manylinux2014_aarch64 --python-version 3.12 --implementation cp --only-binary=:all: --no-compile -r backend/requirements-runtime.txt
.venv\Scripts\python.exe scripts/package_lambda.py
# After source edits, refresh the generated source without deleting dependency data:
.venv\Scripts\python.exe scripts/package_lambda.py --refresh
```

Review `cdk diff` before each named-stack deployment. `scripts/check_template.py` rejects stale bundled source, unexpected resources/IAM and embedded secrets. After the CDK-owned empty secret exists, `scripts/publish_ai_credentials.py` privately populates it from ignored local configuration, guarded by account/stack ownership. Never put keys in CLI arguments, CDK context, logs or templates. Historical Phase 1/2 AWS audits encode their old route/resource counts; use `audit_phase3.py` for the current deployed stack.
