package com.tokenjunkielabs.proofpocket.ui

import android.app.Activity
import android.content.ContentResolver
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.OpenableColumns
import android.text.InputFilter
import android.view.View
import android.widget.*
import com.tokenjunkielabs.proofpocket.billing.BillingState
import com.tokenjunkielabs.proofpocket.billing.RevenueCatGate
import com.tokenjunkielabs.proofpocket.core.DocumentResult
import com.tokenjunkielabs.proofpocket.core.DocumentWork
import com.tokenjunkielabs.proofpocket.core.Evidence
import com.tokenjunkielabs.proofpocket.core.EvidenceStreams
import com.tokenjunkielabs.proofpocket.core.UnicodeIntegrity
import com.tokenjunkielabs.proofpocket.core.Receipt
import com.tokenjunkielabs.proofpocket.core.ReceiptCodec
import com.tokenjunkielabs.proofpocket.core.ReceiptEngine
import com.tokenjunkielabs.proofpocket.core.ReceiptImportLimits
import com.tokenjunkielabs.proofpocket.export.PdfExporter
import com.tokenjunkielabs.proofpocket.store.ProjectDraft
import com.tokenjunkielabs.proofpocket.store.ProofRepository
import java.io.IOException
import java.time.Instant

class MainActivity : Activity() {
    companion object {
        private const val PICK_EVIDENCE = 41
        private const val EXPORT_JSON = 42
        private const val EXPORT_PDF = 43
        private const val IMPORT_RECEIPT = 44
        private const val FREE_PROJECT_LIMIT = 3
    }

    private lateinit var repo: ProofRepository
    private lateinit var billing: RevenueCatGate
    private lateinit var documents: DocumentWork
    private val projects = mutableListOf<ProjectDraft>()
    private val controls = mutableListOf<View>()
    private var selected = 0
    private var pendingRequest = 0
    private var pendingReceipt: Receipt? = null
    private var pendingEvidenceProjectId: String? = null

    private lateinit var projectSpinner: Spinner
    private lateinit var titleInput: EditText
    private lateinit var claimInput: EditText
    private lateinit var evidenceView: TextView
    private lateinit var billingView: TextView
    private lateinit var statusView: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        repo = ProofRepository(this)
        projects += repo.load()
        billing = RevenueCatGate(this)
        // Retain work, not an Activity or a View, while a document provider runs.
        val handler = Handler(Looper.getMainLooper())
        documents = (lastNonConfigurationInstance as? DocumentWork)
            ?: DocumentWork { action -> handler.post { action() } }
        pendingRequest = savedInstanceState?.getInt("pendingRequest") ?: 0
        pendingEvidenceProjectId = savedInstanceState?.getString("pendingEvidenceProjectId")
        pendingReceipt = savedInstanceState?.getString("pendingReceipt")?.let { raw ->
            val (receipt, verification) = ReceiptCodec.decodeAndVerify(raw)
            receipt.takeIf { verification.valid }
        }
        setContentView(buildUi())
        val restoredProjectId = savedInstanceState?.getString("selectedProjectId")
        val restoredIndex = projects.indexOfFirst { it.id == restoredProjectId }.coerceAtLeast(0)
        if (projects.isEmpty()) addProject("First proof project") else refreshSpinner(restoredIndex)
        status(savedInstanceState?.getString("status") ?: "")
        if (savedInstanceState?.getBoolean("documentBusy") == true && lastNonConfigurationInstance == null) {
            status("Document operation was interrupted. Attach or import again; an export may be incomplete.")
        }
        documents.attach(::documentCompleted)
        updateControls()
        billing.configure(::renderBilling)
    }

    private fun buildUi(): View {
        val scroll = ScrollView(this)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 28, 32, 48)
        }
        scroll.addView(root)
        root.addView(TextView(this).apply { text = "ProofPocket"; textSize = 28f })
        root.addView(TextView(this).apply { text = "Local, content-addressed work receipts. Evidence files never leave the device through ProofPocket." })

        fun button(label: String, action: () -> Unit) {
            val button = Button(this).apply { text = label; setOnClickListener { action() } }
            controls += button
            root.addView(button)
        }

        projectSpinner = Spinner(this).also { spinner ->
            spinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onNothingSelected(parent: AdapterView<*>?) = Unit
                override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                    if (position in projects.indices && position != selected && !documents.busy && pendingRequest == 0) {
                        saveCurrent()
                        refreshSpinner(position)
                    }
                }
            }
            controls += spinner
            root.addView(spinner)
        }
        button("New project", ::createProjectTapped)
        titleInput = EditText(this).apply {
            hint = "Project title"
            filters = arrayOf(InputFilter.LengthFilter(160))
        }.also { controls += it; root.addView(it) }
        claimInput = EditText(this).apply {
            hint = "Bounded completion claim"
            minLines = 3
            filters = arrayOf(InputFilter.LengthFilter(2000))
        }.also { controls += it; root.addView(it) }
        button("Attach local evidence", ::pickEvidence)
        evidenceView = TextView(this).also(root::addView)
        button("Create / verify receipt") { createReceipt() }
        button("Export JSON receipt", ::exportJson)
        button("Import + verify receipt", ::importReceipt)
        button("Export Pro PDF proof pack", ::exportPdf)

        billingView = TextView(this).also(root::addView)
        button("Unlock Pro") { billing.purchaseCurrent(this, ::renderBilling) }
        button("Restore purchases") { billing.restore(::renderBilling) }
        statusView = TextView(this).apply { setPadding(0, 24, 0, 0) }.also(root::addView)
        return scroll
    }

    private fun createProjectTapped() {
        saveCurrent()
        if (!billing.isPro() && projects.size >= FREE_PROJECT_LIMIT) {
            status("Free tier allows $FREE_PROJECT_LIMIT projects. RevenueCat Pro entitlement is required for more.")
            return
        }
        addProject("Project ${projects.size + 1}")
    }

    private fun addProject(title: String) {
        projects += repo.newProject(title)
        repo.save(projects)
        refreshSpinner(projects.lastIndex)
    }

    private fun refreshSpinner(select: Int = selected) {
        selected = select.coerceIn(0, projects.lastIndex.coerceAtLeast(0))
        projectSpinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, projects.map { it.title })
        if (projects.isNotEmpty()) {
            projectSpinner.setSelection(selected)
            renderProject(selected)
        }
    }

    private fun renderProject(index: Int) {
        selected = index
        val p = projects[index]
        titleInput.setText(p.title)
        claimInput.setText(p.claim)
        evidenceView.text = if (p.evidence.isEmpty()) "No evidence attached" else p.evidence.joinToString("\n") {
            "• ${it.name} · ${it.sizeBytes} B · ${it.sha256.take(16)}…"
        }
    }

    private fun saveCurrent() {
        if (projects.isEmpty() || selected !in projects.indices || !::titleInput.isInitialized) return
        projects[selected].title = titleInput.text.toString().trim().ifBlank { projects[selected].title }
        projects[selected].claim = claimInput.text.toString().trim()
        repo.save(projects)
    }

    private fun pickEvidence() {
        saveCurrent()
        val project = projects.getOrNull(selected) ?: return
        if (project.evidence.size >= 128) { status("A receipt supports at most 128 evidence items."); return }
        pendingEvidenceProjectId = project.id
        launchPicker(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            type = "*/*"
            addCategory(Intent.CATEGORY_OPENABLE)
        }, PICK_EVIDENCE)
    }

    private fun createReceipt(): Receipt? {
        saveCurrent()
        val p = projects.getOrNull(selected) ?: return null
        return try {
            ReceiptEngine.issue(p.id, p.title, p.claim, Instant.now().toString(), p.evidence).also {
                status("Receipt valid: ${it.receiptId}")
            }
        } catch (e: IllegalArgumentException) {
            status("Cannot issue receipt: ${e.message}")
            null
        }
    }

    private fun exportJson() {
        val receipt = createReceipt() ?: return
        pendingReceipt = receipt
        launchPicker(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            type = "application/json"
            addCategory(Intent.CATEGORY_OPENABLE)
            putExtra(Intent.EXTRA_TITLE, "proofpocket-${receipt.receiptId.take(12)}.json")
        }, EXPORT_JSON)
    }

    private fun exportPdf() {
        if (!billing.isPro()) { status("PDF proof packs require an observed active RevenueCat Pro entitlement."); return }
        val receipt = createReceipt() ?: return
        pendingReceipt = receipt
        launchPicker(Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            type = "application/pdf"
            addCategory(Intent.CATEGORY_OPENABLE)
            putExtra(Intent.EXTRA_TITLE, "proofpocket-${receipt.receiptId.take(12)}.pdf")
        }, EXPORT_PDF)
    }

    private fun importReceipt() {
        saveCurrent()
        launchPicker(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            type = "application/json"
            addCategory(Intent.CATEGORY_OPENABLE)
        }, IMPORT_RECEIPT)
    }

    private fun launchPicker(intent: Intent, requestCode: Int) {
        pendingRequest = requestCode
        updateControls()
        try {
            startActivityForResult(intent, requestCode)
        } catch (e: Exception) {
            clearPendingPicker()
            status("Cannot open document picker: ${e.message ?: "no document provider available"}")
        }
    }

    private fun clearPendingPicker() {
        pendingRequest = 0
        pendingReceipt = null
        pendingEvidenceProjectId = null
        updateControls()
    }

    @Deprecated("Legacy callback keeps this carrier dependency-light and API-26 compatible")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != pendingRequest || pendingRequest == 0) return
        val receipt = pendingReceipt
        val projectId = pendingEvidenceProjectId
        clearPendingPicker()
        if (resultCode != RESULT_OK) { status("Document selection cancelled"); return }
        val uri = data?.data
        if (uri == null) { status("No document was returned by the picker"); return }
        // Application resolver and immutable snapshots only: never capture this
        // Activity in an operation that can outlive it during rotation.
        val resolver = applicationContext.contentResolver
        when (requestCode) {
            PICK_EVIDENCE -> {
                if (projectId == null) { status("Evidence target was lost. Select the project and attach again."); return }
                runDocument("Hashing evidence locally…") {
                    val name = evidenceName(resolver, uri)
                    val mimeType = resolver.getType(uri) ?: "application/octet-stream"
                    require(name.trim().length in 1..255) { "evidence name must be 1..255 chars" }
                    require(mimeType.trim().length in 1..127) { "mime type must be present" }
                    UnicodeIntegrity.requireWellFormedUtf16(name, "evidence name")
                    UnicodeIntegrity.requireWellFormedUtf16(mimeType, "mime type")
                    val input = resolver.openInputStream(uri) ?: throw IOException("unable to read selected evidence")
                    val measured = input.use(EvidenceStreams::hash)
                    val evidence = Evidence(ReceiptEngine.evidenceId(measured.sha256), name, mimeType, measured.sha256, measured.sizeBytes)
                    DocumentResult.Attached(projectId, evidence)
                }
            }
            EXPORT_JSON, EXPORT_PDF -> {
                if (receipt == null) { status("Receipt export was interrupted. Create the receipt and export again."); return }
                val format = if (requestCode == EXPORT_JSON) "JSON receipt" else "PDF proof pack"
                runDocument("Exporting $format…") {
                    try {
                        val output = resolver.openOutputStream(uri, "wt")
                            ?: throw IOException("unable to open selected output document")
                        output.use {
                            if (requestCode == EXPORT_JSON) it.write(ReceiptEngine.exportJson(receipt).toByteArray(Charsets.UTF_8))
                            else PdfExporter.write(receipt, it)
                        }
                        DocumentResult.Message("$format exported")
                    } catch (e: Exception) {
                        throw IOException("$format export failed; the selected document may be incomplete. ${e.message ?: "Try exporting again."}", e)
                    }
                }
            }
            IMPORT_RECEIPT -> runDocument("Reading receipt…") {
                val input = resolver.openInputStream(uri) ?: throw IOException("unable to read selected receipt")
                val raw = input.use(ReceiptImportLimits::readUtf8Bounded)
                val (_, verification) = ReceiptCodec.decodeAndVerify(raw)
                DocumentResult.Message(if (verification.valid) "Imported receipt verified" else "Imported receipt rejected: ${verification.reason}")
            }
        }
    }

    private fun runDocument(message: String, work: () -> DocumentResult) {
        try {
            documents.start(work)
            status(message)
        } catch (e: Exception) {
            status("Document operation could not start: ${e.message}")
        }
        updateControls()
    }

    private fun documentCompleted(result: Result<DocumentResult>) {
        result.fold(onSuccess = { completed ->
            when (completed) {
                is DocumentResult.Message -> status(completed.text)
                is DocumentResult.Attached -> {
                    val project = projects.find { it.id == completed.projectId }
                    when {
                        project == null -> status("Evidence target no longer exists. Nothing was attached.")
                        project.evidence.any { it.id == completed.evidence.id } -> status("That exact evidence content is already attached")
                        project.evidence.size >= 128 -> status("A receipt supports at most 128 evidence items. Nothing was attached.")
                        else -> {
                            project.evidence += completed.evidence
                            repo.save(projects)
                            if (projects.getOrNull(selected)?.id == project.id) renderProject(selected)
                            status("Evidence hashed locally and attached: ${completed.evidence.sizeBytes} bytes")
                        }
                    }
                }
            }
        }, onFailure = { status("Document operation failed: ${it.message ?: "unreadable document"}") })
        updateControls()
    }

    private fun updateControls() {
        val enabled = !documents.busy && pendingRequest == 0
        controls.forEach { it.isEnabled = enabled }
    }

    private fun renderBilling(state: BillingState) {
        runOnUiThread {
            billingView.text = when (state) {
                BillingState.NotConfigured -> "RevenueCat: not configured — public SDK key required; Pro remains locked"
                BillingState.Loading -> "RevenueCat: checking entitlement…"
                is BillingState.Ready -> "RevenueCat: ${if (state.pro) "Pro active" else "Free"} — ${state.message}"
                is BillingState.Error -> "RevenueCat: ${state.message}; Pro remains locked"
            }
        }
    }

    private fun status(message: String) { statusView.text = message }

    override fun onSaveInstanceState(outState: Bundle) {
        saveCurrent()
        outState.putString("selectedProjectId", projects.getOrNull(selected)?.id)
        outState.putInt("pendingRequest", pendingRequest)
        outState.putString("pendingEvidenceProjectId", pendingEvidenceProjectId)
        outState.putString("pendingReceipt", pendingReceipt?.let(ReceiptEngine::exportJson))
        outState.putBoolean("documentBusy", documents.busy)
        outState.putString("status", statusView.text.toString())
        super.onSaveInstanceState(outState)
    }

    @Deprecated("Retain only the document worker; it never owns the Activity")
    override fun onRetainNonConfigurationInstance(): Any = documents

    override fun onStop() { saveCurrent(); super.onStop() }

    override fun onDestroy() {
        documents.detach()
        if (!isChangingConfigurations) documents.close()
        super.onDestroy()
    }
}

private fun evidenceName(resolver: ContentResolver, uri: Uri): String {
    resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
        val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
        if (cursor.moveToFirst() && nameIndex >= 0) {
            return cursor.getString(nameIndex)?.takeIf { it.isNotBlank() } ?: "evidence"
        }
    }
    return "evidence"
}
