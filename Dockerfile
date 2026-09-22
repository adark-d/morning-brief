# syntax=docker/dockerfile:1@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32

FROM public.ecr.aws/lambda/python:3.14@sha256:f42182f21a6b87e85c461eee77e17449cdb631df71953909e7dc89cc65760b8c AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.12@sha256:3a59a3cdd5f7c217faa36e32dbc7fddbb0412889c2a0a5229f6d790e5a019dd7 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_INSTALLER_METADATA=1

# Cache dependencies separately from application code.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv export --frozen --no-dev --no-emit-project -o /tmp/requirements.txt > /dev/null \
    && uv pip install --target /install -r /tmp/requirements.txt

FROM public.ecr.aws/lambda/python:3.14@sha256:f42182f21a6b87e85c461eee77e17449cdb631df71953909e7dc89cc65760b8c

COPY --from=builder /install ${LAMBDA_TASK_ROOT}
COPY src/ai_brief ${LAMBDA_TASK_ROOT}/ai_brief
COPY src/brief_core ${LAMBDA_TASK_ROOT}/brief_core

CMD ["ai_brief.handler.run_handler"]
