# QuickBook DevOps Handbook

`index.html` is a self-contained page (Mermaid is bundled into the image at build time, so it works offline).

```bash
docker compose -f docs/handbook/docker-compose.yml up -d --build   # build + start
open http://localhost:8099
```
`restart: always` restarts it after a crash and every time Docker Desktop starts. For it to come
back after a reboot, enable **Docker Desktop → Settings → General → Start Docker Desktop when you sign in**.
