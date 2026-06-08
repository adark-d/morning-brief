# syntax=docker/dockerfile:1

# morning-brief container image for AWS Lambda — one image, two entry points.
#
# The scheduled-brief function runs the default CMD (run_handler); the API function
# overrides CMD to morning_brief.aws_handlers.api_handler. Both share this image so
# the LLM gateway, guardrails, and audit store are byte-for-byte identical across
# the batch and request paths (ADR 0001 §4.1).
#
# Build and runtime both use the AWS Lambda Python base image (Amazon Linux 2023) so
# native wheels (pandas, numpy, pydantic-core, curl-cffi) are resolved for the exact
# runtime platform. The build stage installs locked dependencies and the project into
# a clean prefix; the runtime stage copies that prefix plus the YAML config into
# ${LAMBDA_TASK_ROOT} (/var/task), which is on the Lambda runtime's import path.

# ---- Build stage: install locked deps + the project into /install ----
FROM public.ecr.aws/lambda/python:3.13 AS builder

# uv gives reproducible, uv.lock-pinned installs. Pinned to match the local toolchain.
COPY --from=ghcr.io/astral-sh/uv:0.11.12 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_INSTALLER_METADATA=1

# 1. Third-party dependencies, pinned by uv.lock (no dev group, project excluded).
#    Bind-mounting the lock + manifest keeps this layer cached until they change,
#    so editing application code never re-resolves dependencies.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv export --frozen --no-dev --no-emit-project -o /tmp/requirements.txt \
    && uv pip install --no-cache --target /install -r /tmp/requirements.txt

# 2. The project itself, installed (not just copied) so its dist-info/METADATA exists:
#    api/app.py reads importlib.metadata.version("morning-brief") when building the app,
#    which raises PackageNotFoundError without installed metadata. --no-deps because the
#    dependency set is already installed and pinned above.
COPY pyproject.toml README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-cache --target /install --no-deps .

# ---- Runtime stage: AWS Lambda Python 3.13 ----
FROM public.ecr.aws/lambda/python:3.13

# Installed dependencies + the morning_brief package (with metadata).
COPY --from=builder /install ${LAMBDA_TASK_ROOT}

# YAML configuration (not part of the wheel — lives at the repo root).
COPY config ${LAMBDA_TASK_ROOT}/config

# Resolve config from the packaged directory: inside the image the package sits
# directly under /var/task (no src/ parent), so the source-tree-relative fallback in
# Settings would point at the wrong place. MORNING_BRIEF_CONFIG_DIR overrides it.
ENV MORNING_BRIEF_CONFIG_DIR=/var/task/config

# Default to the scheduled-brief handler; the API Lambda overrides this CMD.
CMD ["morning_brief.aws_handlers.run_handler"]
