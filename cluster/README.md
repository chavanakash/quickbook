# Kubernetes cluster (kubeadm on Lima VMs)

A real 3-node cluster built by hand with **kubeadm** on a Mac (Apple Silicon), using
[Lima](https://lima-vm.io) to run Ubuntu 24.04 VMs.

| VM | Role | IP | Size |
|---|---|---|---|
| k8s-master | control plane (API server, etcd, scheduler, controller-manager) | 192.168.104.4 | 2 CPU / 3 GB |
| k8s-worker1 | worker | 192.168.104.5 | 2 CPU / 3 GB |
| k8s-worker2 | worker | 192.168.104.6 | 2 CPU / 3 GB |

Container runtime **containerd** · CNI **Flannel** (10.244.0.0/16) · Kubernetes **v1.34** ·
storage **local-path-provisioner** · ingress **Traefik**.

## 1. Create the VMs (Mac)
```bash
brew install lima
limactl start --tty=false --name=k8s-master  --cpus=2 --memory=3 --disk=20 --vm-type=vz \
  --network=lima:user-v2 --set '.portForwards += [{"guestPort":6443,"hostPort":16443}]' template:ubuntu-24.04
limactl start --tty=false --name=k8s-worker1 --cpus=2 --memory=3 --disk=20 --vm-type=vz --network=lima:user-v2 template:ubuntu-24.04
limactl start --tty=false --name=k8s-worker2 --cpus=2 --memory=3 --disk=20 --vm-type=vz --network=lima:user-v2 template:ubuntu-24.04
```
`lima:user-v2` puts all VMs on one shared network so they can reach each other.

## 2. Prepare every node
[`node-setup.sh`](node-setup.sh): disables swap, loads `overlay`/`br_netfilter`, enables IP forwarding,
installs containerd (systemd cgroups) and kubeadm/kubelet/kubectl.
```bash
for n in k8s-master k8s-worker1 k8s-worker2; do limactl shell $n sudo bash "$PWD/cluster/node-setup.sh"; done
```

## 3. Control plane (inside k8s-master)
```bash
sudo kubeadm init --apiserver-advertise-address=$(hostname -I | awk '{print $1}') \
  --pod-network-cidr=10.244.0.0/16 --apiserver-cert-extra-sans=127.0.0.1,localhost
mkdir -p ~/.kube && sudo cp /etc/kubernetes/admin.conf ~/.kube/config && sudo chown $(id -u):$(id -g) ~/.kube/config
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
kubeadm token create --print-join-command
```

## 4. Join the workers (Mac)
```bash
limactl shell k8s-worker1 sudo kubeadm join <master-ip>:6443 --token <token> --discovery-token-ca-cert-hash sha256:<hash>
limactl shell k8s-worker2 sudo kubeadm join <master-ip>:6443 --token <token> --discovery-token-ca-cert-hash sha256:<hash>
```

## 5. kubectl from the Mac
```bash
limactl shell k8s-master sudo cat /etc/kubernetes/admin.conf > ~/.kube/kubeadm-config
sed -i '' 's#server: https://.*:6443#server: https://127.0.0.1:16443#' ~/.kube/kubeadm-config
export KUBECONFIG=~/.kube/config:~/.kube/kubeadm-config
kubectl config use-context kubernetes-admin@kubernetes && kubectl get nodes
```

## 6. Cluster add-ons
```bash
# storage (kubeadm has no default StorageClass)
kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.30/deploy/local-path-storage.yaml
kubectl patch storageclass local-path -p '{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```
Then: ingress → [`ingress/`](../ingress/README.md), monitoring → [`monitoring/`](../monitoring/README.md).

## Day-to-day
```bash
# limactl takes one VM per command. Stop workers first, start the master first.
for vm in k8s-worker1 k8s-worker2 k8s-master; do limactl stop $vm; done    # free ~9 GB RAM
for vm in k8s-master k8s-worker1 k8s-worker2; do limactl start $vm; done
limactl shell k8s-master                           # SSH-like shell into a node
```

## Why not Multipass?
Multipass' bundled `qemu-img` crashed (SIGSEGV) on this Mac. Lima uses Apple's Virtualization
framework (`--vm-type=vz`) instead of QEMU and worked first time.
