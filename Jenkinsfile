// QuickBook CI/CD pipeline
//   CI: test + build images in two parallel batches of 3 -> push to Docker Hub
//   CD: deploy to Kubernetes -> wait for rollout -> smoke test -> auto-rollback on failure
//
// Image tag format: <app>-<build number>, e.g. dockerizzz/quickbook-auth-service:auth-service-12
// The git commit is stored inside each image as the OCI label org.opencontainers.image.revision.
//
// Jenkins credentials this pipeline expects (Manage Jenkins -> Credentials):
//   dockerhub             Username with password  (Docker Hub user + access token)
//   kubeconfig-quickbook  Secret file             (output of ci/jenkins/make-kubeconfig.sh)

// Runs one app's unit tests (Dockerfile "test" stage), then builds its runtime image.
def testAndBuild(String app) {
    def context = (app == 'frontend') ? 'frontend' : "services/${app}"
    sh """
        echo "==> ${app}: unit tests"
        docker build --target test ${context}
        echo "==> ${app}: runtime image"
        docker build \
            --label org.opencontainers.image.revision=${env.GIT_COMMIT} \
            --label org.opencontainers.image.source=https://github.com/chavanakash/quickbook \
            -t ${env.REGISTRY_NAMESPACE}/quickbook-${app}:${app}-${env.BUILD_NUMBER} \
            ${context}
    """
}

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
        DOCKER_BUILDKIT = '1'                // BuildKit: parallel stages, layer cache, cache mounts
        REGISTRY_NAMESPACE = 'dockerizzz'
        APPS = 'auth-service inventory-service booking-service payment-service ticket-service frontend'
        NAMESPACE = 'quickbook'
    }

    stages {
        stage('Prepare') {
            steps {
                script {
                    currentBuild.displayName = "#${env.BUILD_NUMBER} ${env.GIT_COMMIT.take(7)}"
                }
                echo "Building commit ${env.GIT_COMMIT}; tags will be <app>-${env.BUILD_NUMBER}"
            }
        }

        // Batch 1 and batch 2 run one after the other; the 3 images inside a batch build in parallel.
        stage('CI: Test & build batch 1') {
            failFast true                    // one failure stops the other branches
            parallel {
                stage('auth-service')      { steps { script { testAndBuild('auth-service') } } }
                stage('inventory-service') { steps { script { testAndBuild('inventory-service') } } }
                stage('booking-service')   { steps { script { testAndBuild('booking-service') } } }
            }
        }

        stage('CI: Test & build batch 2') {
            failFast true
            parallel {
                stage('payment-service')   { steps { script { testAndBuild('payment-service') } } }
                stage('ticket-service')    { steps { script { testAndBuild('ticket-service') } } }
                stage('frontend')          { steps { script { testAndBuild('frontend') } } }
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
                            docker push $REGISTRY_NAMESPACE/quickbook-$a:$a-$BUILD_NUMBER
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
                            kustomize edit set image $REGISTRY_NAMESPACE/quickbook-$a:$a-$BUILD_NUMBER
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
                                if [ "$current" = "$REGISTRY_NAMESPACE/quickbook-$a:$a-$BUILD_NUMBER" ]; then
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
            // Images are on Docker Hub now; remove local tags. BuildKit's layer/cache-mount cache is kept,
            // so the next build reuses unchanged layers and downloaded packages.
            sh '''
                for a in $APPS; do
                    docker rmi $REGISTRY_NAMESPACE/quickbook-$a:$a-$BUILD_NUMBER > /dev/null 2>&1 || true
                done
                docker image prune -f > /dev/null 2>&1 || true
            '''
            cleanWs()
        }
    }
}
