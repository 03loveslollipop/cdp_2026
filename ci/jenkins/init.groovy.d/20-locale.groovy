// Persist the requested Japanese UI and build-message locale.
def locale = hudson.plugins.locale.PluginImpl.get()
locale.setSystemLocale('ja')
locale.setIgnoreAcceptLanguage(true)
locale.setAllowUserPreferences(false)
locale.save()
hudson.plugins.locale.PluginImpl.init()
