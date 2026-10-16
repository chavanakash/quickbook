#!/usr/bin/env bash
# Run a k6 profile as a Job in the cluster and wait for its verdict.
# Usage: loadtest/run-k6.sh <profile: gate|stress> [job-name]     (uses the current KUBECONFIG)
# Exit code: 0 = thresholds passed, 1 = failed (thresholds breached or job error).
set -euo pipefail
PROFILE=${1:-gate}
NAME=${2:-k6-$PROFILE-$(date +%s)}
DIR=$(cd "$(dirname "$0")" && pwd)
NS=quickbook

kubectl -n $NS create configmap k6-quickbook --from-file="$DIR/k6/quickbook.js" --dry-run=client -o yaml | kubectl apply -f -
sed "s/__NAME__/$NAME/g; s/__PROFILE__/$PROFILE/g" "$DIR/k6/job.yaml" | kubectl apply -f -
echo "k6 job $NAME ($PROFILE) started"

# Wait for the Job to finish either way (kubectl wait can only wait for one condition).
for _ in $(seq 1 180); do
  ok=$(kubectl -n $NS get job "$NAME" -o jsonpath='{.status.succeeded}')
  bad=$(kubectl -n $NS get job "$NAME" -o jsonpath='{.status.failed}')
  [ -n "$ok$bad" ] && break
  sleep 5
done
kubectl -n $NS logs "job/$NAME" --tail=80 || true
if [ "${ok:-0}" = "1" ]; then echo "k6 $PROFILE: PASSED"; exit 0; fi
echo "k6 $PROFILE: FAILED (thresholds breached or job error)"; exit 1
