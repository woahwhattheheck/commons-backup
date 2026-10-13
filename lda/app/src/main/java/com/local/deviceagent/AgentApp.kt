package com.local.deviceagent

import android.app.Activity
import android.app.Application
import android.content.Context
import android.os.Bundle

/**
 * App entry point. Its one job today is to stamp EVERY screen with the ownership label (via an
 * activity lifecycle callback) so "Property of Bryce Muhlnickel" is present at all times without
 * having to touch each Activity individually - and any future screen gets it automatically too.
 */
class AgentApp : Application() {
    // CRASH RECORDER installed as EARLY as possible: attachBaseContext runs BEFORE ContentProviders
    // and before onCreate, so even a provider-init / very-early startup crash is captured. The owner
    // has no adb; the ChatActivity viewer (the REAL launcher) shows this on the next launch. Own prefs
    // so it works even if SettingsManager is the crasher; commit() so it flushes before the process dies.
    override fun attachBaseContext(base: Context?) {
        super.attachBaseContext(base)
        try {
            val prior = Thread.getDefaultUncaughtExceptionHandler()
            Thread.setDefaultUncaughtExceptionHandler { t, e ->
                val trace = java.util.Date().toString() + "\n" + android.util.Log.getStackTraceString(e)
                try {
                    getSharedPreferences("agent_crash", MODE_PRIVATE).edit()
                        .putString("last", trace).commit()
                } catch (_: Throwable) {}
                // ALSO mirror to an external file the owner can pull over USB/Files (no adb) - so a crash
                // BEFORE ChatActivity (which the on-screen viewer can never display) or a crash loop that
                // overwrites the pref is still retrievable. Append so a loop can't erase earlier traces.
                try {
                    getExternalFilesDir(null)?.let {
                        java.io.File(it, "last_crash.txt").appendText(trace + "\n\n======== ======== ========\n\n")
                    }
                } catch (_: Throwable) {}
                prior?.uncaughtException(t, e)
            }
        } catch (_: Throwable) {}
    }

    override fun onCreate() {
        super.onCreate()
        registerActivityLifecycleCallbacks(object : Application.ActivityLifecycleCallbacks {
            override fun onActivityCreated(a: Activity, b: Bundle?) {}
            // After onStart the content view exists, so the stamp lands on top of it. The helper is
            // idempotent (skips if already stamped), so re-entering a screen won't double it.
            // WRAPPED: stamping runs on EVERY activity's start, so a bug here would crash every screen
            // on launch - if the stamp is the launch crash, this try/catch alone fixes it.
            override fun onActivityStarted(a: Activity) { try { Ui.stampBrand(a); Ui.stampBackButton(a) } catch (_: Throwable) {} }
            override fun onActivityResumed(a: Activity) { try { Ui.stampBrand(a); Ui.stampBackButton(a) } catch (_: Throwable) {} }
            override fun onActivityPaused(a: Activity) {}
            override fun onActivityStopped(a: Activity) {}
            override fun onActivitySaveInstanceState(a: Activity, b: Bundle) {}
            override fun onActivityDestroyed(a: Activity) {}
        })
    }
}
