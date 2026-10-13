package com.local.deviceagent

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Source contract: every owner activation reaches the service directly, without an app auth gate. */
class OpenActivationContractTest {

    @Test fun testActivationActionsDispatchDirectly() {
        val service = source("AgentService.kt")
        assertTrue(service.contains("ACTION_LISTEN_NOW -> onListenNow()"))
        assertTrue(service.contains("ACTION_LEARN_MODE -> startLearnMode()"))
        assertTrue(service.contains("ACTION_AUTO_MODE -> toggleAutoMode()"))
        assertTrue(service.contains("pendingContinuous = true"))
        assertTrue(service.contains("if (cmd.isNotBlank()) {"))
        assertFalse(service.contains("gateActivation("))
        assertFalse(service.contains("AuthGateActivity"))
        assertFalse(service.contains("needsReauth"))
    }

    @Test fun testAuthActivityAndPreferencesAreAbsent() {
        val root = projectRoot()
        assertFalse(File(root, "app/src/main/java/com/local/deviceagent/AuthGateActivity.kt").exists())
        val settings = source("SettingsManager.kt")
        assertFalse(settings.contains("biometric_required"))
        assertFalse(settings.contains("reauth_minutes"))
        assertFalse(settings.contains("last_auth_ms"))
        val settingsUi = source("SettingsActivity.kt")
        assertFalse(settingsUi.contains("Require fingerprint / PIN to activate"))
        val ui = source("Ui.kt")
        assertTrue(ui.contains("if (content.childCount == 0) return"))
        assertFalse(ui.contains("auth gate"))
        val manifest = File(root, "app/src/main/AndroidManifest.xml").readText()
        assertFalse(manifest.contains("AuthGateActivity"))
    }

    private fun source(name: String): String =
        File(projectRoot(), "app/src/main/java/com/local/deviceagent/$name").readText()

    private fun projectRoot(): File {
        var dir = File(System.getProperty("user.dir"))
        repeat(8) {
            if (File(dir, "app/src/main/AndroidManifest.xml").isFile) return dir
            dir = dir.parentFile ?: throw AssertionError("LDA project root not found from ${System.getProperty("user.dir")}")
        }
        throw AssertionError("LDA project root not found from ${System.getProperty("user.dir")}")
    }
}
