// QuickBook CI/CD pipeline
//   CI: unit tests (inside Docker) -> build images -> push to Docker Hub
//   CD: deploy to Kubernetes -> wait for rollout -> smoke test -> auto-rollback on failure
//
// Jenkins credentials this pipeline expects (Manage Jenkins -> Credentials):
//   dockerhub             Username with password  (Docker Hub user + access token)
//   kubeconfig-quickbook  Secret file             (output of ci/jenkins/make-kubeconfig.sh)

pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()            // two deploys at once would fight each other
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 30, unit: 'MINUTES')
    }

    triggers {
        // GitHub webhooks can't reach Jenkins on a laptop, so poll the repo every ~2 minutes.
        pollSCM('H/2 * * * *')
    }

    environment {
        REGISTRY_NAMESPACE = 'dockerizzz'
        SERVICES = 'auth-service inventory-service booking-service payment-service ticket-service'
        APPS = 'auth-service inventory-service booking-service payment-service ticket-service frontend'
        NAMESPACE = 'quickbook'
    }

    stages {
        stage('Prepare') {
            steps {
                script {
                    // Tag = build number + commit, so every running image maps to an exact commit.
                    def commit = sh(script: 'git rev-parse --short=7 HEAD', returnStdout: true).trim()
                    env.IMAGE_TAG = "${env.BUILD_NUMBER}-${commit}"
                    currentBuild.displayName = "#${env.BUILD_NUMBER} ${env.IMAGE_TAG}"
                }
                echo "Image tag for this build: ${env.IMAGE_TAG}"
            }
        }

        stage('CI: Unit tests') {
            steps {
                // Each Dockerfile has a "test" stage; the build fails if any test fails.
                sh '''
                    for s in $SERVICES; do
                        echo "==> testing $s"
                        docker build --target test services/$s
                    done
                    echo "==> testing frontend"
                    docker build --target test frontend
                '''
            }
        }

        stage('CI: Build images') {
            steps {
                sh '''
                    for s in $SERVICES; do
                        docker build -t $REGISTRY_NAMESPACE/quickbook-$s:$IMAGE_TAG services/$s
                    done
                    docker build -t $REGISTRY_NAMESPACE/quickbook-frontend:$IMAGE_TAG frontend
                '''
            }
        }

        stage('CI: Push images') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'dockerhub',
                                                  usernameVariable: 'DOCKER_USER',
                                                  passwordVariable: 'DOCKER_TOKEN')]) {
                    // Throwaway Docker config dir: the login never persists on the Jenkins host.
                    sh '''
                        export DOCKER_CONFIG=$(mktemp -d)
                        trap 'rm -rf "$DOCKER_CONFIG"' EXIT
                        echo "$DOCKER_TOKEN" | docker login -u "$DOCKER_USER" --password-stdin
                        for a in $APPS; do
                            docker push $REGISTRY_NAMESPACE/quickbook-$a:$IMAGE_TAG
                        done
                    '''
                }
            }
        }

        stage('CD: Deploy to Kubernetes') {
            steps {
                withCredentials([file(credentialsId: 'kubeconfig-quickbook', variable: 'KUBECONFIG')]) {
                    // Point the manifests at this build's images (workspace copy only, not committed).
                    sh '''
                        cd k8s
                        for a in $APPS; do
                            kustomize edit set image $REGISTRY_NAMESPACE/quickbook-$a:$IMAGE_TAG
                        done
                        grep -A1 "name: $REGISTRY_NAMESPACE" kustomization.yaml
                    '''
                    script { env.DEPLOY_STARTED = 'true' }
                    sh 'kubectl apply -k k8s'
                    sh '''
                        for a in $APPS; do
                            kubectl -n $NAMESPACE rollout status deployment/$a --timeout=180s
                        done
                    '''
                }
            }
        }

        stage('CD: Smoke test') {
            steps {
                withCredentials([file(credentialsId: 'kubeconfig-quickbook', variable: 'KUBECONFIG')]) {
                    // End-to-end flow through the real gateway: signup -> book -> pay -> PDF.
                    sh '''
                        kubectl -n $NAMESPACE port-forward svc/frontend 18080:80 > port-forward.log 2>&1 &
                        PF_PID=$!
                        trap 'kill $PF_PID 2>/dev/null' EXIT
                        for i in $(seq 1 30); do
                            curl -sf http://localhost:18080/nginx-health > /dev/null && break
                            sleep 1
                        done
                        python3 scripts/smoke_test.py http://localhost:18080
                    '''
                }
            }
        }
    }

    post {
        failure {
            script {
                if (env.DEPLOY_STARTED == 'true') {
                    withCredentials([file(credentialsId: 'kubeconfig-quickbook', variable: 'KUBECONFIG')]) {
                        // Undo only deployments that are on THIS build's image; never touch the others.
                        sh '''
                            for a in $APPS; do
                                current=$(kubectl -n $NAMESPACE get deployment $a -o jsonpath='{.spec.template.spec.containers[0].image}')
                                if [ "$current" = "$REGISTRY_NAMESPACE/quickbook-$a:$IMAGE_TAG" ]; then
                                    echo "==> rolling back $a"
                                    kubectl -n $NAMESPACE rollout undo deployment/$a || true
                                fi
                            done
                        '''
                    }
                }
            }
        }
        always {
            // Images are on Docker Hub now; free local disk on the Docker Desktop VM.
            sh '''
                for a in $APPS; do
                    docker rmi $REGISTRY_NAMESPACE/quickbook-$a:$IMAGE_TAG > /dev/null 2>&1 || true
                done
                docker image prune -f > /dev/null 2>&1 || true
            '''
            cleanWs()
        }
    }
}
