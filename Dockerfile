FROM mcr.microsoft.com/playwright:v1.55.0-noble

ARG PDIIIF_SENTRY_DSN
ARG PDIIIF_SENTRY_TUNNEL_ENDPOINT

ENV PDIIIF_SENTRY_DSN=${PDIIIF_SENTRY_DSN}
ENV PDIIIF_SENTRY_TUNNEL_ENDPOINT=${PDIIIF_SENTRY_TUNNEL_ENDPOINT}

RUN npm install -g pnpm@10.12.4

WORKDIR /app

COPY pnpm-lock.yaml pnpm-workspace.yaml ./
COPY package.json ./

COPY pdiiif-api/package.json ./pdiiif-api/
COPY pdiiif-lib/package.json ./pdiiif-lib/
COPY pdiiif-web/package.json ./pdiiif-web/

RUN pnpm install --frozen-lockfile

COPY . .

RUN pnpm run -r build

RUN rm -rf ~/.pnpm-store ~/.local/share/pnpm/store

ENV CFG_PORT=8080
ENV CFG_HOST=0.0.0.0

EXPOSE 8080

WORKDIR /app/pdiiif-api

CMD ["node", "dist/server.js"]