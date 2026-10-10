# LLD-5 change 1: Bedrock setup and smoke test (code side)

Brief from ARCHITECT-8 (M-199), saved for the team.

Settings live in `backend/.env` (git-ignored); `backend/.env.example` lists the names only:
`BEDROCK_REGION`, `BEDROCK_TEXT_MODEL`, `BEDROCK_VISION_MODEL`, `AWS_PROFILE`, `AI_ENABLED` (true/false).

1. `backend/.env.example` with those names (empty values, `AI_ENABLED=false`, short comments). `backend/.env` is git-ignored (root `.gitignore`).
2. `backend/app/agents/config.py`: loads `backend/.env` (python-dotenv) and exposes a frozen `Settings` dataclass via `get_settings()` with `region`, `text_model`, `vision_model`, `aws_profile`, `ai_enabled: bool` (default False when missing). If `ai_enabled` but a model or region is missing, raise a clear config error naming the missing setting. No secret values are logged (there are none here; AWS credentials stay in the AWS CLI profile).
3. `backend/app/agents/smoke.py`, run as `python -m app.agents.smoke` from `backend/`: using the Strands Agents SDK (`strands-agents`) with a `BedrockModel` built from `Settings` (model_id, region, boto session from `AWS_PROFILE`), send one tiny text prompt to the text model and one prompt with a tiny generated PNG to the vision model; print both replies and the elapsed seconds; exit 0 on success. On missing settings, missing credentials, access denied or timeout (10 s each), print one plain-words line saying what is wrong and which setup step fixes it (e.g. `run aws sts get-caller-identity --profile hackmidwest`), exit 1. `AWS_PROFILE` etc. are left to the environment, never hardcoded.
4. Pin `strands-agents` (and `python-dotenv`, `boto3` if used directly) in `backend/requirements.txt`, keeping existing lines.
5. Tests in `backend/tests/test_agents_config.py`: settings parsing (true/false/missing), missing-setting error, smoke exits 1 with a clear message when AI settings are absent (no network). No live AWS call in tests.

No AWS credentials exist on the laptop yet; none are created here.
