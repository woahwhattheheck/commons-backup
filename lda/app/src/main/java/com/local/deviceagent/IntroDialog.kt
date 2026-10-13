package com.local.deviceagent

import android.content.Context
import androidx.appcompat.app.AlertDialog

/**
 * The startup "How it works" intro: what the agent does, that it EXPERIMENTS and learns, the safety
 * settings, and that everything stays on-device. Shown once per cold start until the owner taps
 * "Don't show again", and always reachable from Settings - How it works.
 */
object IntroDialog {

    private val MESSAGE = """
        This agent runs entirely on your phone. It acts like you do — reading the screen and tapping and typing to carry out tasks you give it by voice or text.

        • It learns by doing. On a new screen it may try a few things, occasionally fumble, then remember what worked for next time. Let it experiment — and keep an eye on it, especially early on.

        • Two modes in the chat, toggled by the Chat / Run button next to the message box: in CHAT mode it just talks with you (answers questions, explains itself — it does NOT touch your apps); in RUN mode what you type is a TASK it carries out on the phone. Tap the button to switch — it shows the mode you're in.

        • You're always in control. Tap the floating button (or say your trigger word) to hand it a task, and tap it again to stop it instantly.

        • The Security settings protect you — it asks first before anything that looks like a payment, a purchase, or a system update. Don't change those unless you know what they do.

        • Nothing leaves your phone. Your tasks, your memory, and everything it learns stay on-device.

        You can reopen this anytime under Settings → How it works.
    """.trimIndent()

    /** [onDone] runs after the dialog is dismissed by any path, so a caller can chain follow-ups. */
    fun show(context: Context, onDone: () -> Unit = {}) {
        AlertDialog.Builder(context)
            .setTitle("How Local Agent works")
            .setMessage(MESSAGE)
            .setNeutralButton("Don't show again") { _, _ -> SettingsManager(context).setIntroHidden(true); onDone() }
            .setPositiveButton("Got it") { _, _ -> onDone() }
            .setOnCancelListener { onDone() }
            .show()
    }
}
