package com.tokenjunkielabs.proofpocket.store

import android.content.Context
import com.tokenjunkielabs.proofpocket.core.Evidence
import com.tokenjunkielabs.proofpocket.core.ReceiptEngine
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

data class ProjectDraft(
    val id: String,
    var title: String,
    var claim: String,
    val createdAtUtc: String,
    val evidence: MutableList<Evidence> = mutableListOf(),
)

class ProofRepository(context: Context) {
    private val prefs = context.getSharedPreferences("proofpocket.v1", Context.MODE_PRIVATE)

    fun load(): MutableList<ProjectDraft> {
        val raw = prefs.getString("projects", null) ?: return mutableListOf()
        return try {
            val arr = JSONArray(raw)
            MutableList(arr.length()) { index ->
                val p = arr.getJSONObject(index)
                val evidenceArray = p.getJSONArray("evidence")
                val evidence = MutableList(evidenceArray.length()) { eIndex ->
                    val e = evidenceArray.getJSONObject(eIndex)
                    Evidence(
                        id = e.getString("id"),
                        name = e.getString("name"),
                        mimeType = e.getString("mimeType"),
                        sha256 = e.getString("sha256"),
                        sizeBytes = e.getLong("sizeBytes"),
                        sourceModifiedAtUtc = if (e.isNull("sourceModifiedAtUtc")) null else e.getString("sourceModifiedAtUtc"),
                    )
                }
                ProjectDraft(
                    id = p.getString("id"),
                    title = p.getString("title"),
                    claim = p.optString("claim", ""),
                    createdAtUtc = p.getString("createdAtUtc"),
                    evidence = evidence,
                )
            }
        } catch (_: Exception) {
            mutableListOf()
        }
    }

    fun newProject(title: String): ProjectDraft {
        val now = Instant.now().toString()
        return ProjectDraft(ReceiptEngine.stableProjectId(title, now), title.trim(), "", now)
    }

    fun save(projects: List<ProjectDraft>) {
        val arr = JSONArray()
        projects.forEach { project ->
            val evidence = JSONArray()
            project.evidence.forEach { item ->
                evidence.put(JSONObject()
                    .put("id", item.id)
                    .put("name", item.name)
                    .put("mimeType", item.mimeType)
                    .put("sha256", item.sha256)
                    .put("sizeBytes", item.sizeBytes)
                    .put("sourceModifiedAtUtc", item.sourceModifiedAtUtc))
            }
            arr.put(JSONObject()
                .put("id", project.id)
                .put("title", project.title)
                .put("claim", project.claim)
                .put("createdAtUtc", project.createdAtUtc)
                .put("evidence", evidence))
        }
        prefs.edit().putString("projects", arr.toString()).apply()
    }
}
