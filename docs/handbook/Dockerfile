# QuickBook DevOps Handbook as a tiny static site.

# ---- fetch: download Mermaid at build time so the page renders diagrams offline ----
FROM alpine:3.20 AS fetch
ARG MERMAID_VERSION=11.4.1
RUN wget -q -O /mermaid.min.js "https://cdn.jsdelivr.net/npm/mermaid@${MERMAID_VERSION}/dist/mermaid.min.js"

# ---- runtime: unprivileged nginx (non-root, listens on 8080) ----
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --from=fetch /mermaid.min.js /usr/share/nginx/html/mermaid.min.js
COPY index.html /usr/share/nginx/html/index.html
EXPOSE 8080
