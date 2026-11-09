// Record the exact branch revision before waiting for the single executor.
// Periodic indexing can then recognize a webhook build already queued for it.
if (env.BRANCH_NAME) {
    assert scm != null
}

pipeline {
    agent any
    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timestamps()
        timeout(time: 45, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }
    // Multibranch discovery handles every repository branch, including branches
    // without a Jenkinsfile, using this shared definition. Only the configured
    // primary branch proceeds from tests to model training and approval.
    // Each discovered child receives GitHub push events. The parent scans Git
    // refs every minute for new branches and as fallback, without REST API quota.
    triggers { githubPush() }
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
                    env.PIPELINE_MODE = (!env.BRANCH_NAME ||
                        env.BRANCH_NAME == (env.SEMESTER_PRIMARY_BRANCH ?: 'master')) ? 'full' : 'tests'
                    currentBuild.description = "${env.BRANCH_NAME ?: 'legacy'} ${env.GIT_COMMIT.take(12)} (${env.PIPELINE_MODE})"
                }
                sh 'git rev-parse HEAD'
            }
        }
        stage('Load shared CI tools') {
            steps {
                script {
                    env.CI_TOOLS = '.'
                    if (env.SEMESTER_CI_REVISION) {
                        dir('.semester-ci') {
                            checkout(changelog: false, poll: false, scm: [
                                $class: 'GitSCM', branches: [[name: env.SEMESTER_CI_REVISION]],
                                userRemoteConfigs: [[url: 'https://github.com/03loveslollipop/cdp_2026.git']]])
                        }
                        env.CI_TOOLS = '.semester-ci'
                    }
                }
            }
        }
        stage('Validate structure') {
            steps { sh 'python "$CI_TOOLS/ci/validate_structure.py" --mode "$PIPELINE_MODE" --without-ci-files' }
        }
        stage('Repository tests') {
            steps {
                sh 'mkdir -p reports && python -m pytest -q tests --junitxml=reports/junit.xml'
            }
        }
        stage('Train and evaluate') {
            when { expression { env.PIPELINE_MODE == 'full' } }
            steps {
                sh '''python -m mlops_pipeline.src.model_training_evaluation \
                    --training-config "$CI_TOOLS/ci/training.json" --output-dir reports/models'''
            }
        }
        stage('Quality and stability') {
            when { expression { env.PIPELINE_MODE == 'full' } }
            steps {
                sh 'python "$CI_TOOLS/ci/check_metrics.py" reports/models --policy "$CI_TOOLS/ci/quality-gates.json"'
                // Make the actual evaluation available while approval is pending.
                archiveArtifacts artifacts: 'reports/models/*summary.csv,reports/models/*metrics.json,reports/models/quality-gate.json,reports/models/selection.json,reports/models/manifest.json,reports/models/report.md,reports/models/figures/*.png',
                    fingerprint: true
            }
        }
        stage('Approve model') {
            when { expression { env.PIPELINE_MODE == 'full' } }
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
            when { expression { env.PIPELINE_MODE == 'full' } }
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
                        script {
                            // A failed source checkout still needs a completion
                            // receipt. Obtain only the pinned notification tools.
                            if (env.SEMESTER_CI_REVISION &&
                                !fileExists("${env.CI_TOOLS ?: '.'}/ci/notify.py")) {
                                dir('.semester-ci') {
                                    checkout(changelog: false, poll: false, scm: [
                                        $class: 'GitSCM', branches: [[name: env.SEMESTER_CI_REVISION]],
                                        userRemoteConfigs: [[url: 'https://github.com/03loveslollipop/cdp_2026.git']]])
                                }
                                env.CI_TOOLS = '.semester-ci'
                            }
                        }
                        sh 'python "${CI_TOOLS:-.}/ci/notify.py"'
                    }
                }
            }
            archiveArtifacts artifacts: 'reports/junit.xml,reports/*.json,reports/approval.txt,reports/models/*summary.csv,reports/models/*metrics.json,reports/models/quality-gate.json,reports/models/selection.json,reports/models/manifest.json,reports/models/status.json,reports/models/report.md,reports/models/figures/*.png',
                allowEmptyArchive: true, fingerprint: true
        }
    }
}
