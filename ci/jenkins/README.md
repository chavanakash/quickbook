# Jenkins CI/CD

Jenkins runs as a container on Docker Desktop and drives the pipeline in the repo's `Jenkinsfile`.

```
GitHub ──(poll every 2 min)──► Jenkins (Docker Desktop)
                                 │ CI: batch 1 ∥ auth, inventory, booking   (test target, then runtime image)
                                 │     batch 2 ∥ payment, ticket, frontend
                                 │     docker push                  ──► Docker Hub (dockerizzz/quickbook-*)
                                 │ CD: kustomize edit set image + kubectl apply -k
                                 │     rollout status + smoke test  ──► kubeadm cluster (namespace quickbook)
                                 └─ on failure after deploy: rollout undo (only deployments on this build's tag)
```

## Files
| File | Purpose |
|---|---|
| `Dockerfile` | Jenkins LTS + docker CLI, kubectl, kustomize, python3 |
| `docker-compose.yml` | runs Jenkins with the Docker socket mounted, UI on :8080 |
| `rbac.yaml` | `jenkins-deployer` service account, limited to the `quickbook` namespace |
| `make-kubeconfig.sh` | builds the kubeconfig Jenkins uses (token for that service account) |

## Setup
```bash
# 1. Start Jenkins
docker compose -f ci/jenkins/docker-compose.yml up -d --build
docker exec quickbook-jenkins cat /var/jenkins_home/secrets/initialAdminPassword

# 2. Cluster access for Jenkins (run with your admin kubeconfig)
kubectl apply -f ci/jenkins/rbac.yaml
ci/jenkins/make-kubeconfig.sh            # writes ~/k8s-lab/jenkins-kubeconfig (do not commit)
```
3. In the UI (http://localhost:8080): install suggested plugins, create the admin user.
4. Add credentials (Manage Jenkins → Credentials → System → Global → Add):
   - `dockerhub`: *Username with password* – Docker Hub username + access token (Read & Write)
   - `kubeconfig-quickbook`: *Secret file* – upload `~/k8s-lab/jenkins-kubeconfig`
5. New Item → **Pipeline** named `quickbook` → *Pipeline script from SCM* → Git →
   `https://github.com/chavanakash/quickbook.git`, branch `*/main`, script path `Jenkinsfile`.

## Notes
- **Tests run inside Docker** (`--target test`), so Jenkins needs no Python/Node toolchains.
- **Image tag** = `<app>-<build number>` (e.g. `auth-service-12`); the commit is in the image label
  `org.opencontainers.image.revision`. The tag edit in `k8s/kustomization.yaml` happens only in the
  Jenkins workspace (not committed back). GitOps (Argo CD) is the next step up from this.
- **Smaller images**: builder stage installs deps into a virtualenv; the Alpine runtime stage copies only that.
- **BuildKit cache**: layer cache persists on Docker Desktop between builds; `RUN --mount=type=cache`
  keeps pip/npm download caches out of the image but reused across builds.
- **Rollback** reverts Deployments only; ConfigMap/Secret changes are not undone automatically.
- **Docker socket access is root-equivalent** on the Docker VM. Fine for a lab; production setups use
  isolated build agents (Kubernetes agents, Kaniko/BuildKit) instead.
