pipeline {
    agent any
    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timestamps()
        timeout(time: 45, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }
    // A GitHub push (including a merged PR's destination-branch push) asks
    // Jenkins to poll the configured SCM branch. Polling is also a fallback
    // when the webhook receiver is unavailable. Neither builds unchanged SCM.
    // Requires the locked "github" plugin and a reachable /github-webhook/.
    triggers {
        githubPush()
        pollSCM('H/2 * * * *')
    }
    environment {
        MPLBACKEND = 'Agg'
        OMP_NUM_THREADS = '2'
        OPENBLAS_NUM_THREADS = '2'
        PYTHONUNBUFFERED = '1'
    }
    stages {
        stage('Clone repository') {
            steps {
                deleteDir()
                script {
                    def revision = checkout(scm)
                    env.GIT_COMMIT = revision.GIT_COMMIT
                }
                sh 'git rev-parse HEAD'
            }
        }
        stage('Validate structure') {
            steps { sh 'python ci/validate_structure.py' }
        }
        stage('Repository tests') {
            steps {
                sh 'mkdir -p reports && python -m pytest -q tests --junitxml=reports/junit.xml'
            }
        }
        stage('Train and evaluate') {
            steps {
                sh '''python -m mlops_pipeline.src.model_training_evaluation \
                    --training-config ci/training.json --output-dir reports/models'''
            }
        }
        stage('Quality and stability') {
            steps {
                sh 'python ci/check_metrics.py reports/models'
                // Make the actual evaluation available while approval is pending.
                archiveArtifacts artifacts: 'reports/models/*summary.csv,reports/models/*metrics.json,reports/models/quality-gate.json,reports/models/selection.json,reports/models/manifest.json,reports/models/report.md,reports/models/figures/*.png',
                    fingerprint: true
            }
        }
        stage('Approve model') {
            steps {
                timeout(time: 20, unit: 'MINUTES') {
                    script {
                        def approval = input(
                            message: 'Review validation metrics, stability and holdout audit. Approve this lab model?',
                            ok: 'Approve model', submitter: 'admin', submitterParameter: 'APPROVER')
                        env.APPROVER = approval instanceof Map ? approval.APPROVER : approval.toString()
                    }
                }
            }
        }
        stage('Record approval') {
            steps {
                writeFile file: 'reports/approval.txt',
                    text: "Approved by ${env.APPROVER}; build ${env.BUILD_URL}; commit ${env.GIT_COMMIT}\n"
                echo 'Model approved. Evaluation artifacts are available on this build.'
            }
        }
    }
    post {
        always {
            junit testResults: 'reports/junit.xml', allowEmptyResults: true
            script {
                withEnv(["PIPELINE_RESULT=${currentBuild.currentResult}"]) {
                    // Notification errors mark the run unstable and remain visible.
                    catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                        sh 'python ci/notify.py'
                    }
                }
            }
            archiveArtifacts artifacts: 'reports/junit.xml,reports/*.json,reports/approval.txt,reports/models/*summary.csv,reports/models/*metrics.json,reports/models/quality-gate.json,reports/models/selection.json,reports/models/manifest.json,reports/models/status.json,reports/models/report.md,reports/models/figures/*.png',
                allowEmptyArchive: true, fingerprint: true
        }
    }
}
