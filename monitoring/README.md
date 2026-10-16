# Monitoring: Prometheus + Grafana + Loki

Metrics: **kube-prometheus-stack** Helm chart. Logs: **Loki** (storage) + **Grafana Alloy** (collector).
Everything runs in the `monitoring` namespace.

```
node-exporter (every node) ─┐  node CPU / memory / disk / network
kubelet + cAdvisor ─────────┤  container CPU / memory per pod
kube-state-metrics ─────────┼─► Prometheus ─► Grafana dashboards
QuickBook services /metrics ┘  HTTP traffic, latency, errors + business metrics
  (selected by servicemonitor.yaml)

all pod logs ──► Alloy (reads them via the K8s API, extracts JSON "level") ──► Loki ──► Grafana
```

| File | Purpose |
|---|---|
| `values.yaml` | kube-prometheus-stack settings sized for the 3 × 3 GB lab cluster (+ Loki datasource) |
| `loki-values.yaml` | Loki in single-binary mode, filesystem storage, 3-day retention |
| `alloy-values.yaml` | Alloy config: discover pods → label → parse JSON level → push to Loki |
| `servicemonitor.yaml` | tells Prometheus to scrape the 5 Python services |
| `dashboards/generate.py` | source of the QuickBook dashboard (edit this, not the JSON) |
| `dashboards/quickbook-overview.json` | generated dashboard, loaded via a labelled ConfigMap |
| `kustomization.yaml` | applies the ServiceMonitor + dashboard ConfigMap |

## Install / upgrade
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Grafana admin login (once; kept out of git)
kubectl create namespace monitoring
kubectl -n monitoring create secret generic grafana-admin \
  --from-literal=admin-user=admin --from-literal=admin-password="$(openssl rand -base64 18 | tr -d '/+=')"

helm upgrade --install monitoring prometheus-community/kube-prometheus-stack --version 92.9.0 \
  -n monitoring -f monitoring/values.yaml
helm upgrade --install loki  grafana/loki  --version 7.3.0  -n monitoring -f monitoring/loki-values.yaml
helm upgrade --install alloy grafana/alloy --version 1.13.1 -n monitoring -f monitoring/alloy-values.yaml

kubectl apply -k monitoring/      # ServiceMonitor + QuickBook dashboard
```

## Open Grafana
```bash
kubectl -n monitoring get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 -d; echo
kubectl -n monitoring port-forward svc/monitoring-grafana 3001:80
```
http://localhost:3001 – user `admin`. Dashboards → **QuickBook Overview**, plus the built-in
"Kubernetes / Compute Resources / …" and "Node Exporter / Nodes" dashboards.

Prometheus UI (targets, ad-hoc queries):
```bash
kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090
```

## Logs in Grafana
- **QuickBook Overview → Logs row**: log volume, errors/warnings per service, and a live log viewer
  (use the `app` and `search logs` boxes at the top).
- **Explore → Loki** for ad-hoc LogQL, e.g.
  ```
  {namespace="quickbook", app="payment-service"} | json | status >= 400
  {namespace="quickbook", level="ERROR"}
  {namespace="quickbook"} | json | request_id="<id from a response header>"   # follow one request
  ```
Labels available: `namespace`, `app`, `pod`, `container`, `node`, `level`.

## QuickBook business metrics
| Metric | Service |
|---|---|
| `quickbook_registered_users` (gauge) | auth |
| `quickbook_signups_total`, `quickbook_signins_total{result}` | auth |
| `quickbook_searches_total{mode}` | inventory |
| `quickbook_bookings_created_total{mode}`, `quickbook_bookings_confirmed_total{mode}` | booking |
| `quickbook_payments_total{status}`, `quickbook_revenue_inr_total` | payment |
| `quickbook_tickets_generated_total` | ticket |

HTTP metrics (`http_requests_total`, `http_request_duration_seconds`) come from
prometheus-fastapi-instrumentator on every service.

## Lab trade-offs
- Alertmanager disabled (no alerting yet).
- kube-controller-manager, scheduler, etcd and kube-proxy are not scraped: kubeadm binds their
  metrics to 127.0.0.1. Rebinding them to 0.0.0.0 is a follow-up exercise.
- Prometheus keeps 3 days / 4 GB of data on a 5 Gi local-path volume; Loki keeps 3 days on 5 Gi.
- Alloy runs as one replica reading logs through the API server – simple, fine for a small cluster.
  Large clusters run it as a DaemonSet tailing `/var/log/pods` on each node.
