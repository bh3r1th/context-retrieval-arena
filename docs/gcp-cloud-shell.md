# Vertex AI from Cloud Shell

Follow the authenticated Cloud Shell / attached-service-account approach used by
`bh3r1th/context-inference-lab`. This project calls managed Gemini on Vertex AI;
it does not need that repository's GPU, vLLM server, Cloud Build, or deployment.
No GCP resource was deployed or paid inference performed while preparing this guide.
The current authorized generation budget remains **US$0**.

## Project and identity

- Project ID: `project-ce0aa110-c8ea-4c1e-80b`
- Project number: `809334676818`
- Vertex AI location: `global`
- Service account: `context-retrieval-arena@project-ce0aa110-c8ea-4c1e-80b.iam.gserviceaccount.com`

The service-account email alone does not authenticate a process. In Cloud Shell,
use ADC with impersonation. On Cloud Run later, attach this service account to
the job and let ADC obtain credentials from the runtime. Neither route requires
downloading a service-account JSON private key or configuring Codex federation.

## 1. GCP prerequisites

Open Google Cloud Console in the intended project and launch Cloud Shell. An
administrator must confirm billing is enabled and the Vertex AI and IAM Service
Account Credentials APIs are enabled. To enable missing APIs, an authorized
administrator can run:

```sh
gcloud services enable aiplatform.googleapis.com iamcredentials.googleapis.com \
  --project=project-ce0aa110-c8ea-4c1e-80b
```

The service account needs **Vertex AI User** (`roles/aiplatform.user`) on the
project. The legacy **AI Platform Admin** role (`roles/ml.admin`) is not the same
role as a Vertex AI role; verify the actual role ID rather than the display name.
Do not assume an existing admin label establishes Vertex authorization.

Your signed-in Google account also needs **Service Account Token Creator**
(`roles/iam.serviceAccountTokenCreator`) on this specific service account to
impersonate it. An IAM administrator can grant that narrowly scoped binding:

```sh
gcloud iam service-accounts add-iam-policy-binding \
  context-retrieval-arena@project-ce0aa110-c8ea-4c1e-80b.iam.gserviceaccount.com \
  --project=project-ce0aa110-c8ea-4c1e-80b \
  --member='user:YOUR_GOOGLE_ACCOUNT_EMAIL' \
  --role=roles/iam.serviceAccountTokenCreator
```

Replace the email with the actual Cloud Shell user. This command changes IAM;
run it only as an administrator intending to grant that user impersonation access.
Quota-project use may also require `serviceusage.services.use` (available through
Service Usage Consumer) on the quota project. Diagnose the actual permission error
before adding grants. No IAM or API settings are modified by the Python CLI.

## 2. Get the source and install

In an existing checkout, pull the commit containing Vertex support. Otherwise:

```sh
git clone https://github.com/bh3r1th/context-retrieval-arena.git
cd context-retrieval-arena
```

Install uv if absent, then install the locked environment:

```sh
python3 -m pip install --user uv
export PATH="$HOME/.local/bin:$PATH"
uv sync --locked --extra gemini
uv run --no-sync python -m unittest discover -s tests -v
```

## 3. Authenticate ADC without an inference request

An authenticated `gcloud` CLI account and Python ADC are separate credential
paths. Establish ADC explicitly for the Python SDK:

```sh
gcloud auth application-default login \
  --impersonate-service-account=context-retrieval-arena@project-ce0aa110-c8ea-4c1e-80b.iam.gserviceaccount.com
gcloud auth application-default set-quota-project project-ce0aa110-c8ea-4c1e-80b
export GOOGLE_CLOUD_PROJECT=project-ce0aa110-c8ea-4c1e-80b
export GOOGLE_CLOUD_LOCATION=global
```

Complete the Google login flow in your browser. Keep ADC files in gcloud's managed
location, outside the repository; never copy them into Git or chat. Do not set
`GOOGLE_APPLICATION_CREDENTIALS` to an unrelated or nonexistent file, since it can
override the ADC selected by gcloud. Preserve any intentionally configured runtime
identity when running on a managed platform.

Check token acquisition without printing the token or calling Gemini:

```sh
uv run --no-sync python - <<'PY'
import google.auth
from google.auth.transport.requests import Request

credentials, project = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)
credentials.refresh(Request())
print("ADC refresh succeeded:", credentials.valid)
print("Quota project:", getattr(credentials, "quota_project_id", None))
PY
```

This contacts authentication/impersonation services only. It verifies credential
refresh, not Vertex API permissions, model availability, context fit, or billing.
Do not use `gcloud auth print-access-token` in logs or paste tokens into chat.

## 4. Prepare inputs locally

Follow [pilot-runbook.md](pilot-runbook.md) to ingest the stored PDF and validate
the 20-question pilot. These commands do not contact Gemini. Existing generated
outputs are intentionally never overwritten; reuse them or choose new paths.

## 5. Later: count prompts with Vertex

Select a supported model ID and verify its current input/output limits in the
[Vertex AI model documentation](https://cloud.google.com/vertex-ai/generative-ai/docs/models).
Do not copy Developer API limits or pricing without verifying Vertex applicability.

The pinned SDK's Vertex `models.get` response does not expose input/output token
limits, so `cra tokens --backend vertex` requires both explicit limits and a source
URL/reference. It records these as **operator-supplied**, not provider-verified.
Exact prompt counts still come from Vertex's `countTokens` endpoint.

After confirming provider terms and authorizing the remote token-count requests:

```sh
uv run --no-sync cra tokens --backend vertex \
  --project project-ce0aa110-c8ea-4c1e-80b --location global \
  --document artifacts/documents/sec-regulation-best-interest-2018/document.json \
  --questions data/datasets/sec-regulation-best-interest-2018/pilot.json \
  --model YOUR_VERIFIED_MODEL_ID --max-output-tokens 2048 \
  --temperature 0 --seed 42 \
  --input-token-limit VERIFIED_INPUT_LIMIT \
  --output-token-limit VERIFIED_OUTPUT_LIMIT \
  --limits-source 'MODEL_DOCUMENTATION_URL_AND_VERSION' \
  --output artifacts/vertex-pilot-tokens.json
```

Replace all uppercase placeholders. `tokens` uploads the full text per question
and never generates answers. At `global`, the inference host is
`aiplatform.googleapis.com`; restricted networks must also permit the authentication
endpoints required by their chosen ADC path. This guide does not change network policy.

## 6. Paid generation remains deferred

Only after a nonzero spending limit is authorized, model/pricing are verified,
and token preflight passes, use the pilot `cra run` command with:

```text
--backend vertex --project project-ce0aa110-c8ea-4c1e-80b --location global
```

Vertex mode uses ADC and does not require `GEMINI_API_KEY` or `GOOGLE_API_KEY`.
The default `--backend developer` still uses API-key authentication; environment
variables do not implicitly switch the backend. No automatic fallback is performed.
Run and token artifacts record backend, project and location; comparison reports
reject runs with different connection settings.

If moving to Cloud Run later, attach the service account as the runtime identity
and retain ADC. The job's compute region is separate from the Vertex `global`
location. Deployment, resource sizing, result persistence and any execution cost
need a separate concrete deployment plan; none has been created or executed here.
