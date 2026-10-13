package com.local.deviceagent

import android.content.Context
import org.vosk.Model
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.zip.ZipInputStream

/**
 * Ensures the small offline Vosk English model is present on the device and
 * loads it. The model (~40 MB) is downloaded once on first run and unzipped
 * into internal storage; subsequent launches load it directly.
 *
 * [loadModel] blocks (network + disk + native load) — always call it off the
 * main thread.
 */
object VoskModelManager {
    private const val MODEL_NAME = "vosk-model-small-en-us-0.15"
    private const val MODEL_URL = "https://alphacephei.com/vosk/models/$MODEL_NAME.zip"

    fun loadModel(context: Context, onProgress: (String) -> Unit): Model {
        val modelDir = File(context.filesDir, MODEL_NAME)
        if (!isUnpacked(modelDir)) {
            onProgress("Downloading voice model…")
            downloadAndUnpack(context, modelDir)
        }
        onProgress("Loading voice model…")
        return Model(modelDir.absolutePath)
    }

    /** A valid model directory contains these Kaldi sub-folders. */
    private fun isUnpacked(modelDir: File): Boolean =
        File(modelDir, "am").isDirectory && File(modelDir, "conf").isDirectory

    private fun downloadAndUnpack(context: Context, modelDir: File) {
        val zipFile = File(context.filesDir, "$MODEL_NAME.zip")
        try {
            val conn = (URL(MODEL_URL).openConnection() as HttpURLConnection).apply {
                connectTimeout = 30_000
                readTimeout = 30_000
            }
            conn.inputStream.use { input ->
                FileOutputStream(zipFile).use { output -> input.copyTo(output) }
            }
            unzip(zipFile, context.filesDir)
        } finally {
            zipFile.delete()
        }
        if (!isUnpacked(modelDir)) throw IllegalStateException("Vosk model unpack failed")
    }

    private fun unzip(zipFile: File, targetDir: File) {
        val canonicalTarget = targetDir.canonicalPath
        ZipInputStream(zipFile.inputStream().buffered()).use { zis ->
            var entry = zis.nextEntry
            while (entry != null) {
                val outFile = File(targetDir, entry.name)
                // Guard against zip-slip path traversal.
                if (!outFile.canonicalPath.startsWith(canonicalTarget + File.separator)) {
                    throw SecurityException("Unsafe zip entry: ${entry.name}")
                }
                if (entry.isDirectory) {
                    outFile.mkdirs()
                } else {
                    outFile.parentFile?.mkdirs()
                    FileOutputStream(outFile).use { fos -> zis.copyTo(fos) }
                }
                zis.closeEntry()
                entry = zis.nextEntry
            }
        }
    }
}
