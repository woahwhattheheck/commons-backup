package com.local.deviceagent

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * JVM unit tests for the W0 screen-class taxonomy (A1 / JEPA world model). This is the H-JEPA abstraction
 * key — a regression here silently re-keys every world-model reference, so pin the deterministic priority
 * order and each class's trigger.
 */
class ScreenClassTest {

    private fun c(pkg: String = "com.example.app", codec: String = "", text: String = "",
                  n: Int = 10, kb: Boolean = false) = ScreenClass.classify(pkg, codec, text, n, kb)

    @Test fun loadingBeatsEverything() {
        assertEquals(ScreenClass.LOADING, c(text = "Loading…", n = 1))
        assertEquals(ScreenClass.LOADING, c(text = "Please wait", n = 3))
    }

    @Test fun errorScreenDetected() {
        assertEquals(ScreenClass.ERROR, c(text = "No internet connection. Try again.", n = 4))
        assertEquals(ScreenClass.ERROR, c(text = "Something went wrong", n = 5))
    }

    @Test fun keyboardUpDominates() {
        // An IME up over a content screen is a keyboard state, not a list.
        assertEquals(ScreenClass.KEYBOARD, c(n = 20, kb = true))
    }

    @Test fun treeEmptyIsCanvas() {
        assertEquals(ScreenClass.CANVAS, c(n = 1))
        assertEquals(ScreenClass.CANVAS, c(n = 2))
    }

    @Test fun launcherIsHome() {
        assertEquals(ScreenClass.HOME, c(pkg = "com.google.android.apps.nexuslauncher", n = 30))
    }

    @Test fun confirmAffordanceIsDialog() {
        assertEquals(ScreenClass.DIALOG, c(text = "Allow app to access photos? Allow Deny", n = 3))
        assertEquals(ScreenClass.DIALOG, c(text = "Delete this item? Cancel OK", n = 4))
    }

    @Test fun settingsByPackageOrToggleDensity() {
        assertEquals(ScreenClass.SETTINGS, c(pkg = "com.android.settings", n = 15))
        // toggle-dense codec (t / * / o after the id) ⇒ settings even without the package hint.
        val codec = "1t Wi-Fi\n2t* Bluetooth\n3to Airplane\n4 Back"
        assertEquals(ScreenClass.SETTINGS, c(pkg = "com.example.app", codec = codec, n = 4))
    }

    @Test fun browserIsWebview() {
        assertEquals(ScreenClass.WEBVIEW, c(pkg = "com.android.chrome", n = 8))
    }

    @Test fun contentScreenIsList() {
        assertEquals(ScreenClass.LIST, c(n = 20))
    }

    @Test fun sparseUnknownIsGeneric() {
        assertEquals(ScreenClass.GENERIC, c(n = 4))
    }

    @Test fun deviceStateOverlay() {
        assertEquals("offline", ScreenClass.deviceState("No internet connection"))
        assertEquals("airplane", ScreenClass.deviceState("Airplane mode is on"))
        assertEquals("", ScreenClass.deviceState("Home"))
    }

    @Test fun navPrimitiveAbstractsVerbs() {
        assertEquals("back", ScreenClass.navPrimitive("back"))
        assertEquals("app-switch", ScreenClass.navPrimitive("open_app"))
        assertEquals("scroll", ScreenClass.navPrimitive("swipe"))
        assertEquals("type", ScreenClass.navPrimitive("set_text"))
        assertEquals("tap", ScreenClass.navPrimitive("click"))
        assertEquals("other", ScreenClass.navPrimitive("reply"))
    }
}
