import jenkins.model.Jenkins
import hudson.security.HudsonPrivateSecurityRealm
import hudson.security.FullControlOnceLoggedInAuthorizationStrategy
import hudson.plugins.git.GitSCM
import hudson.plugins.git.UserRemoteConfig
import hudson.plugins.git.BranchSpec
import org.jenkinsci.plugins.workflow.job.WorkflowJob
import org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition
import jenkins.model.JenkinsLocationConfiguration

def j = Jenkins.get()
def realm = new HudsonPrivateSecurityRealm(false)
if (j.securityRealm instanceof HudsonPrivateSecurityRealm) {
    realm = j.securityRealm
}
if (realm.getUser('admin') == null) {
    realm.createAccount('admin', new File('/run/secrets/jenkins_admin_password').text.trim())
}
j.setSecurityRealm(realm)
def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
strategy.setAllowAnonymousRead(false)
j.setAuthorizationStrategy(strategy)
j.setNumExecutors(1)
def location = JenkinsLocationConfiguration.get()
location.setUrl(System.getenv('JENKINS_LAB_URL') ?: 'http://127.0.0.1:18081/')
location.save()
j.setSystemMessage('Credit Classification semester lab — local Jenkins, CPU tests, model quality and human approval.')
def job = j.getItem('credit-classification')
if (job == null) {
    job = j.createProject(WorkflowJob, 'credit-classification')
    def remote = System.getenv('REPOSITORY_URL') ?: 'file:///opt/source'
    def branch = System.getenv('REPOSITORY_BRANCH') ?: 'ci-review'
    def scm = new GitSCM([new UserRemoteConfig(remote, null, null, null)],
        [new BranchSpec('*/' + branch)], false, [], null, null, [])
    def definition = new CpsScmFlowDefinition(scm, 'Jenkinsfile')
    definition.setLightweight(false)
    job.setDefinition(definition)
    job.setDescription('Clone → validate → repository tests → temporal training → metric/stability gates → administrator approval → local completion notification')
    job.save()
}
j.save()
