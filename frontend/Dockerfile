# Multi-stage build: Node is only used to build; the final image is nginx + static files.

# ---- deps: install node modules and copy the source ----
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# BuildKit cache mount: npm's download cache is reused across builds, not stored in the image.
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .

# ---- test: CI runs `docker build --target test` ----
FROM deps AS test
RUN npm test

# ---- build: produce the static site ----
FROM deps AS build
RUN npm run build

# ---- runtime (default target) ----
# The unprivileged image runs as non-root and listens on 8080.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
