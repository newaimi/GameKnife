FROM node:20.19-slim AS community-web

WORKDIR /app
COPY package.json package-lock.json ./
COPY tsconfig.base.json ./
COPY packages ./packages
COPY apps/community-web/package.json ./apps/community-web/package.json
RUN npm install
COPY apps/community-web ./apps/community-web
RUN npm --workspace apps/community-web run build

FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY apps/community-api ./apps/community-api
COPY services ./services
COPY --from=community-web /app/apps/community-web/dist ./apps/community-web/dist
RUN pip install --no-cache-dir -e .
ENV GAMEKNIFE_WEB_DIST=/app/apps/community-web/dist
CMD ["uvicorn", "community_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
