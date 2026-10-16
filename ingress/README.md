# Ingress (Traefik)

Stable URLs for the lab cluster – no `kubectl port-forward` needed.

| URL | Goes to |
|---|---|
| http://quickbook.localhost:8088 | QuickBook (frontend Service; nginx routes `/api/*` to the services) |
| http://grafana.localhost:8088 | Grafana (user `admin`, password in Secret `monitoring/grafana-admin`) |
| http://prometheus.localhost:8088 | Prometheus UI |

```
browser ─► localhost:8088 (Mac) ─► Lima auto port-forward ─► k8s-master:8088 (Traefik, hostNetwork)
                                                               └─► Service by Host header ─► pods
```

## Install
```bash
helm repo add traefik https://traefik.github.io/charts && helm repo update
helm upgrade --install traefik traefik/traefik --version 42.0.0 -n traefik --create-namespace \
  -f ingress/traefik-values.yaml
```
Routes live with what they expose: `k8s/ingress.yaml` (deployed by Jenkins with the app) and
`monitoring/ingress.yaml` (applied with `kubectl apply -k monitoring/`).

One-time on the Mac (curl/Chrome/Firefox resolve `*.localhost` themselves; Safari, Python and
other macOS apps need this):
```bash
echo "127.0.0.1 quickbook.localhost grafana.localhost prometheus.localhost" | sudo tee -a /etc/hosts
```

## Why these choices
- **Traefik**, not ingress-nginx: the ingress-nginx project was retired in March 2026.
- **hostNetwork on the master**: Lima forwards real listening sockets from the VM to the Mac, so
  Traefik must open :8088 on the node itself. Port 8088 because Jenkins already uses 8080 on the Mac;
  Traefik's metrics moved to 9102 because node-exporter owns 9100 on every node.
- Production equivalent: a `LoadBalancer` Service (cloud LB or MetalLB) in front of 2+ Traefik pods,
  plus real DNS and TLS certificates (cert-manager).
