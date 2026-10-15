# Kubernetes deployment

Plain manifests, assembled with Kustomize (`kubectl apply -k`).

| File | What it creates |
|---|---|
| `namespace.yaml` | `quickbook` namespace |
| `configmap.yaml` | non-secret settings (service URLs, log level) |
| `secrets.yaml` | JWT secret, internal token, per-service DB URLs, Postgres password (lab only!) |
| `postgres/` | init SQL (Secret) + Postgres StatefulSet with a 2Gi PersistentVolume + headless Service |
| `services/*.yaml` | one Deployment + Service per microservice and the frontend |
| `kustomization.yaml` | lists everything and pins image tags |

Every app Deployment has: 2 replicas spread across nodes, rolling updates with zero downtime,
startup/liveness/readiness probes, CPU/memory requests and limits, non-root security context,
and Prometheus scrape annotations.

## One-time cluster prerequisite (kubeadm has no storage provisioner)
```bash
kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.30/deploy/local-path-storage.yaml
kubectl patch storageclass local-path -p '{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```

## Deploy
```bash
kubectl apply -k k8s/
kubectl -n quickbook get pods -o wide -w
```

## Open the app
```bash
kubectl -n quickbook port-forward svc/frontend 3000:80
open http://localhost:3000
python3 scripts/smoke_test.py http://localhost:3000
```

## Useful commands
```bash
kubectl -n quickbook logs -l app=booking-service -f           # logs of all booking pods
kubectl -n quickbook rollout restart deployment/auth-service  # restart pods one by one
kubectl -n quickbook rollout undo deployment/auth-service     # roll back to previous version
kubectl -n quickbook scale deployment/ticket-service --replicas=3
kubectl delete namespace quickbook                            # remove everything (incl. DB data)
```
