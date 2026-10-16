#!/bin/bash
set -euo pipefail
K8S_VERSION=v1.34

echo "==> 1. Disable swap (kubelet requires it off)"
swapoff -a
sed -i '/ swap / s/^/#/' /etc/fstab

echo "==> 2. Kernel modules + sysctl (lets pod traffic pass through the Linux bridge)"
cat > /etc/modules-load.d/k8s.conf <<EOF
overlay
br_netfilter
EOF
modprobe overlay
modprobe br_netfilter
cat > /etc/sysctl.d/k8s.conf <<EOF
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
sysctl --system > /dev/null

echo "==> 3. Install containerd (the container runtime)"
apt-get update -q
apt-get install -y -q containerd apt-transport-https ca-certificates curl gpg
mkdir -p /etc/containerd
containerd config default > /etc/containerd/config.toml
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
systemctl restart containerd
systemctl enable containerd

echo "==> 4. Install kubeadm, kubelet, kubectl ($K8S_VERSION)"
mkdir -p -m 755 /etc/apt/keyrings
curl -fsSL https://pkgs.k8s.io/core:/stable:/${K8S_VERSION}/deb/Release.key | gpg --dearmor --yes -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/${K8S_VERSION}/deb/ /" > /etc/apt/sources.list.d/kubernetes.list
apt-get update -q
apt-get install -y -q kubelet kubeadm kubectl
apt-mark hold kubelet kubeadm kubectl
systemctl enable --now kubelet

echo "==> Checks"
grep 'SystemdCgroup = true' /etc/containerd/config.toml
kubeadm version -o short
echo "==> Node ready for kubeadm init/join"
