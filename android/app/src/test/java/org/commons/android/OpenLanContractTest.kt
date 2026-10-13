package org.commons.android

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Source contract: the wireless TITAN host is credential-free, matching LDA LAN. */
class OpenLanContractTest {
    @Test
    fun pairingAdmissionIsAbsent() {
        val root = projectRoot()
        assertFalse(File(root, "src/main/java/org/commons/android/Pairing.kt").exists())
        val server = read("HttpJsonServer.kt")
        val host = read("TitanHandsHostService.kt")
        val activity = read("MainActivity.kt")
        listOf("PAIRING_REQUIRED", "PAIRING_MISMATCH", "expectedPairing", "publicHealth", "Pairing.mint").forEach {
            assertFalse("pairing admission remains: $it", server.contains(it))
            assertFalse("pairing admission remains in host: $it", host.contains(it))
        }
        assertFalse(server.contains("X-Commons-Pairing"))
        assertFalse(activity.contains("need the on-device pairing code"))
        assertFalse(activity.contains("Pairing code"))
        assertFalse(activity.contains("Not an open LAN drive"))
        assertTrue(activity.contains("Possessing the LAN URL"))
        val strings = File(projectRoot(), "src/main/res/values/strings.xml").readText()
        assertFalse(strings.contains("pairing code"))
        assertTrue(strings.contains("credential-free"))
        assertTrue(server.contains("bindHost"))
        assertTrue(host.contains("bindHost = \"0.0.0.0\""))
        assertTrue(activity.contains("host running (user-started)"))
    }

    private fun read(name: String): String =
        File(projectRoot(), "src/main/java/org/commons/android/$name").readText()

    private fun projectRoot(): File {
        var dir = File(System.getProperty("user.dir"))
        repeat(8) {
            if (File(dir, "src/main/AndroidManifest.xml").isFile) return dir
            if (File(dir, "app/src/main/AndroidManifest.xml").isFile) return File(dir, "app")
            dir = dir.parentFile ?: throw AssertionError("android project root not found")
        }
        throw AssertionError("android project root not found from ${System.getProperty("user.dir")}")
    }
}
