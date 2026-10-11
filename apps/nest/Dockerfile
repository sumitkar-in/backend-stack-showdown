# syntax=docker/dockerfile:1
ARG NODE_IMAGE=node:22-slim

FROM ${NODE_IMAGE} AS build
WORKDIR /src
COPY package.json package-lock.json* ./
# npm ci when a lockfile exists (commit package-lock.json after the first build)
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

FROM ${NODE_IMAGE} AS deps
WORKDIR /src
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --omit=dev; else npm install --omit=dev; fi

FROM ${NODE_IMAGE}
WORKDIR /app
ENV NODE_ENV=production TZ=Asia/Kolkata APP_WORKERS=2 DB_POOL_PER_WORKER=10 UV_THREADPOOL_SIZE=4 NODE_OPTIONS=--max-old-space-size=1536
COPY --from=deps /src/node_modules ./node_modules
COPY --from=build /src/dist ./dist
COPY package.json ./
USER node
EXPOSE 8080
CMD ["node", "dist/main.js"]
