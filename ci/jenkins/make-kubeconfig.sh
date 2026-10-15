#!/usr/bin/env bash
# Builds a kubeconfig for Jenkins from the jenkins-deployer service account.
# Usage: ci/jenkins/make-kubeconfig.sh [output-file]   (run with an admin kubeconfig/context)
# The output contains a token: upload it to Jenkins as a "Secret file" credential, never commit it.
set -euo pipefail
OUT=${1:-$HOME/k8s-lab/jenkins-kubeconfig}

TOKEN=$(kubectl -n quickbook get secret jenkins-deployer-token -o jsonpath='{.data.token}' | base64 -d)
CA=$(kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')

# Jenkins runs in Docker Desktop, so it reaches the Mac's port-forward (16443) via host.docker.internal.
# That name is not in the API server certificate, so verify TLS against the name "kubernetes", which is.
umask 077
cat > "$OUT" <<KUBECONFIG
apiVersion: v1
kind: Config
clusters:
  - name: quickbook-lab
    cluster:
      server: https://host.docker.internal:16443
      tls-server-name: kubernetes
      certificate-authority-data: ${CA}
users:
  - name: jenkins-deployer
    user:
      token: ${TOKEN}
contexts:
  - name: jenkins@quickbook-lab
    context:
      cluster: quickbook-lab
      user: jenkins-deployer
      namespace: quickbook
current-context: jenkins@quickbook-lab
KUBECONFIG
echo "Wrote $OUT"
