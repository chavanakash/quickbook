# Monitoring: Prometheus + Grafana

Installed with the **kube-prometheus-stack** Helm chart into the `monitoring` namespace.

```
node-exporter (every node) ─┐  node CPU / memory / disk / network
kubelet + cAdvisor ─────────┤  container CPU / memory per pod
kube-state-metrics ─────────┼─► Prometheus ─► Grafana dashboards
QuickBook services /metrics ┘  HTTP traffic, latency, errors + business metrics
  (selected by servicemonitor.yaml)
```

| File | Purpose |
|---|---|
| `values.yaml` | chart settings sized for the 3 × 3 GB lab cluster |
| `servicemonitor.yaml` | tells Prometheus to scrape the 5 Python services |
| `dashboards/generate.py` | source of the QuickBook dashboard (edit this, not the JSON) |
| `dashboards/quickbook-overview.json` | generated dashboard, loaded via a labelled ConfigMap |
| `kustomization.yaml` | applies the ServiceMonitor + dashboard ConfigMap |

## Install / upgrade
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --version 92.9.0 --namespace monitoring --create-namespace \
  -f monitoring/values.yaml \
  --set grafana.adminPassword="$(openssl rand -base64 18 | tr -d '/+=')"   # only on first install

kubectl apply -k monitoring/
```

## Open Grafana
```bash
kubectl -n monitoring get secret monitoring-grafana -o jsonpath='{.data.admin-password}' | base64 -d; echo
kubectl -n monitoring port-forward svc/monitoring-grafana 3001:80
```
http://localhost:3001 – user `admin`. Dashboards → **QuickBook Overview**, plus the built-in
"Kubernetes / Compute Resources / …" and "Node Exporter / Nodes" dashboards.

Prometheus UI (targets, ad-hoc queries):
```bash
kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090
```

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
- Prometheus keeps 3 days / 4 GB of data on a 5 Gi local-path volume.
