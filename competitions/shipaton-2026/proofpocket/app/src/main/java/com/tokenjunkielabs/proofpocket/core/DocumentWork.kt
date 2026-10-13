package com.tokenjunkielabs.proofpocket.core

import java.util.concurrent.Executors

sealed class DocumentResult {
    data class Attached(val projectId: String, val evidence: Evidence) : DocumentResult()
    data class Message(val text: String) : DocumentResult()
}

/** One document operation survives an Activity configuration change.
 * Call public methods on the UI thread. [dispatch] must return work to that
 * thread without retaining the Activity. Work closures use application-scoped
 * services; detach the UI listener before the old Activity is destroyed.
 */
class DocumentWork(private val dispatch: (() -> Unit) -> Unit) {
    private val executor = Executors.newSingleThreadExecutor()
    private var listener: ((Result<DocumentResult>) -> Unit)? = null
    private var completed: Result<DocumentResult>? = null
    private var closed = false
    var busy: Boolean = false
        private set

    fun attach(listener: (Result<DocumentResult>) -> Unit) {
        this.listener = listener
        deliver()
    }

    fun detach() { listener = null }

    fun start(work: () -> DocumentResult) {
        check(!closed && !busy && completed == null) { "another document operation is still pending" }
        busy = true
        executor.execute {
            val result = try { Result.success(work()) } catch (e: Exception) { Result.failure(e) }
            dispatch {
                busy = false
                if (!closed) {
                    completed = result
                    deliver()
                }
            }
        }
    }

    fun close() {
        closed = true
        detach()
        completed = null
        executor.shutdownNow()
    }

    private fun deliver() {
        val consumer = listener ?: return
        val result = completed ?: return
        completed = null
        consumer(result)
    }
}
