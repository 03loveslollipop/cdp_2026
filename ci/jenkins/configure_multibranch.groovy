// Execute through the authenticated Jenkins script console. Replace the two
// JSON string placeholders using ci/configure_multibranch.py before submission.
import groovy.json.JsonOutput
import jenkins.model.Jenkins
import hudson.plugins.git.GitSCM
import hudson.plugins.git.UserRemoteConfig
import hudson.plugins.git.BranchSpec
import hudson.slaves.EnvironmentVariablesNodeProperty
import jenkins.branch.BranchSource
import com.cloudbees.hudson.plugins.folder.computed.DefaultOrphanedItemStrategy
import org.jenkinsci.plugins.github_branch_source.GitHubSCMSource
import org.jenkinsci.plugins.github_branch_source.BranchDiscoveryTrait
import org.jenkinsci.plugins.workflow.multibranch.WorkflowMultiBranchProject
import org.jenkinsci.plugins.workflow.multibranch.extended.RemoteJenkinsFileWorkflowBranchProjectFactory
import org.jenkinsci.plugins.workflow.multibranch.extended.scm.ExcludeFromChangeSet
import org.jenkinsci.plugins.workflow.multibranch.extended.scm.ExcludeFromPoll
import com.cloudbees.hudson.plugins.folder.computed.PeriodicFolderTrigger

def revision = __CI_REVISION_JSON__
def primaryBranch = __PRIMARY_BRANCH_JSON__
assert revision ==~ /[a-f0-9]{40}/
assert primaryBranch in ['main', 'master']
def j = Jenkins.get()
def environmentMessage = 'Jenkins on GCP VM semester-jenkins (nb-core-dev-99d0). Browser access uses a private IAP tunnel.'
j.setSystemMessage(environmentMessage)
def environmentInit = new File(j.rootDir, 'init.groovy.d/90-gcp-environment.groovy')
environmentInit.parentFile.mkdirs()
environmentInit.text = 'jenkins.model.Jenkins.get().setSystemMessage(' +
    JsonOutput.toJson(environmentMessage) + '); jenkins.model.Jenkins.get().save()\n'
def name = 'credit-classification-branches'
def existing = j.getItem(name)
assert existing == null || existing instanceof WorkflowMultiBranchProject
def legacy = j.getItem('credit-classification-github')
assert legacy == null || !legacy.isBuilding()
def env = j.globalNodeProperties.get(EnvironmentVariablesNodeProperty)
if (env == null) {
    env = new EnvironmentVariablesNodeProperty()
    j.globalNodeProperties.add(env)
}
env.envVars.put('SEMESTER_CI_REVISION', revision)
env.envVars.put('SEMESTER_PRIMARY_BRANCH', primaryBranch)
def project = existing ?: j.createProject(WorkflowMultiBranchProject, name)
def source = new GitHubSCMSource('03loveslollipop', 'cdp_2026', null, false)
source.setId('credit-classification-all-branches')
source.setTraits([new BranchDiscoveryTrait(3)])
project.sourcesList.replaceBy([new BranchSource(source)])
def shared = new GitSCM([
    new UserRemoteConfig('https://github.com/03loveslollipop/cdp_2026.git', null, null, null)],
    [new BranchSpec(revision)], false, [], null, null,
    [new ExcludeFromChangeSet(), new ExcludeFromPoll()])
project.setProjectFactory(new RemoteJenkinsFileWorkflowBranchProjectFactory(
    'Jenkinsfile', '', shared, false, primaryBranch, false))
project.setOrphanedItemStrategy(new DefaultOrphanedItemStrategy(true, '7', '20'))
project.addTrigger(new PeriodicFolderTrigger('1h'))
project.setDescription('All repository branches: clone and tests. Push/merge to ' + primaryBranch +
    ': tests, CPU training, quality/stability, admin approval and notification. Shared Jenkinsfile pinned to ' +
    revision + '. Existing lab cleanup deadline: 2026-11-13 02:41:05 UTC.')
project.save()
if (legacy != null) {
    legacy.setDisabled(true)
    legacy.setDescription('Historical single-branch push/merge evidence. Replaced by ' + name + '; history retained.')
    legacy.save()
}
j.save()
project.scheduleBuild2(0)
println(JsonOutput.toJson([job: project.fullName, primary_branch: primaryBranch,
    discovery: 'all origin branches, including those without a Jenkinsfile',
    ci_revision: revision, legacy_disabled: legacy?.isDisabled(), indexing_scheduled: true]))
