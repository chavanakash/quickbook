# Jenkins controller with the CLI tools our pipeline needs.
# Pinned version = reproducible; bump deliberately.
FROM jenkins/jenkins:2.580.1-lts-jdk21

USER root

# Docker CLI only (no daemon): builds run on Docker Desktop's engine via the mounted socket.
# python3: runs scripts/smoke_test.py (standard library only).
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg python3 \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
      > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends docker-ce-cli docker-buildx-plugin \
 && rm -rf /var/lib/apt/lists/*

# kubectl matching the cluster's minor version (v1.34), and kustomize for "edit set image".
ARG KUBECTL_VERSION=v1.34.1
ARG KUSTOMIZE_VERSION=v5.4.3
RUN ARCH=$(dpkg --print-architecture) \
 && curl -fsSL -o /usr/local/bin/kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${ARCH}/kubectl" \
 && chmod +x /usr/local/bin/kubectl \
 && curl -fsSL "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2F${KUSTOMIZE_VERSION}/kustomize_${KUSTOMIZE_VERSION}_linux_${ARCH}.tar.gz" \
      | tar -xz -C /usr/local/bin kustomize

USER jenkins
