pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // sherpa-onnx (speech to text, text to speech) is published only here.
        maven("https://jitpack.io") { content { includeGroupByRegex("com\\.github\\.k2-fsa.*") } }
    }
}
rootProject.name = "FastChatGlasses"
include(":app")
