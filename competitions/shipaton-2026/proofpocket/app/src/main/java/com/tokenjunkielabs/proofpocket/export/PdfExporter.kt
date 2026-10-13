package com.tokenjunkielabs.proofpocket.export

import android.graphics.Paint
import android.graphics.pdf.PdfDocument
import com.tokenjunkielabs.proofpocket.core.Receipt
import java.io.OutputStream

object PdfExporter {
    fun write(receipt: Receipt, output: OutputStream) {
        val document = PdfDocument()
        val paint = Paint().apply { textSize = 12f }
        val titlePaint = Paint().apply { textSize = 20f; isFakeBoldText = true }
        val page = document.startPage(PdfDocument.PageInfo.Builder(612, 792, 1).create())
        val c = page.canvas
        var y = 52f
        c.drawText("ProofPocket proof pack", 48f, y, titlePaint); y += 34f
        listOf(
            "Receipt: ${receipt.receiptId}",
            "Project: ${receipt.projectTitle}",
            "Issued: ${receipt.issuedAtUtc}",
            "Claim: ${receipt.claim}",
            "Evidence (${receipt.evidence.size}):",
        ).forEach { line -> c.drawText(line.take(92), 48f, y, paint); y += 22f }
        receipt.evidence.forEachIndexed { i, e ->
            if (y > 730f) return@forEachIndexed
            c.drawText("${i + 1}. ${e.name.take(54)}  sha256=${e.sha256.take(20)}…  ${e.sizeBytes} B", 58f, y, paint)
            y += 18f
        }
        document.finishPage(page)
        document.writeTo(output)
        document.close()
    }
}
