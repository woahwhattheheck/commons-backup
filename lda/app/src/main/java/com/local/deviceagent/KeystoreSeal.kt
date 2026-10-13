package com.local.deviceagent

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * DATA-AT-REST SEAL for the crown-jewel journals (param-mod hardening). AES-256-GCM under a NON-EXPORTABLE
 * AndroidKeyStore key, so a file that leaks (root, a pulled `filesDir`) is opaque bytes — the plaintext never
 * touches disk. The point: the WeightGenome edit-journal IS the literal map of the weight-modification method
 * (`{seed, [pos, origByte]…}`); plaintext on disk, a single `cat` reverse-engineers the whole technique even
 * with the writer flag off. Sealing it closes that no-decompiler leak (the R8 class-rename doesn't touch data
 * files; `allowBackup=false` only stopped `adb backup`, not a rooted read).
 *
 * The key is device-bound and never leaves the Keystore, so the seal can only be opened ON this device — an
 * exfiltrated file cannot be decrypted off-device even with the APK. Each record is `base64(iv ‖ gcm_ciphertext)`
 * on its own line, so append + rolling-trim semantics are preserved (per-line, not whole-file).
 *
 * SAFE-BY-DESIGN: every call is guarded and FAIL-OPEN toward the caller's existing best-effort contract — a seal
 * failure returns null so the journal write is simply skipped (never crashes the evolve/bake beat), and `open()`
 * returns null on any legacy/corrupt/foreign line so it is skipped rather than throwing. Losing an unreadable
 * journal line only forfeits that beat's precise undo; the baseline backup + brick-guard remain the safety net.
 */
object KeystoreSeal {
    private const val ALIAS = "lda_seal_v1"
    private const val IV_LEN = 12          // GCM standard nonce length
    private const val TAG_BITS = 128

    private fun secretKey(): SecretKey? = try {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey) ?: run {
            val kg = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
            kg.init(
                KeyGenParameterSpec.Builder(ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256)
                    .build())
            kg.generateKey()
        }
    } catch (_: Throwable) { null }

    /** Encrypt [plain] → `base64(iv ‖ ciphertext+tag)`, or null on any failure (caller then skips the write). */
    fun seal(plain: String): String? = try {
        val key = secretKey() ?: return null
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key) }
        val iv = cipher.iv                                   // GCM generates a fresh IV per encrypt — never reuse one
        val ct = cipher.doFinal(plain.toByteArray(Charsets.UTF_8))
        Base64.encodeToString(iv + ct, Base64.NO_WRAP)
    } catch (_: Throwable) { null }

    /** Decrypt a `seal()` line back to UTF-8, or null for a legacy/corrupt/foreign line (caller then skips it).
     *  Block body (not expression body) because the guards use `return null` — Kotlin prohibits `return` in an
     *  expression-body function (the CI compile error at 43b31d3). */
    fun open(sealed: String): String? {
        return try {
            val blob = Base64.decode(sealed.trim(), Base64.NO_WRAP)
            if (blob.size <= IV_LEN) return null
            val key = secretKey() ?: return null
            val iv = blob.copyOfRange(0, IV_LEN)
            val ct = blob.copyOfRange(IV_LEN, blob.size)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
                init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(TAG_BITS, iv))
            }
            String(cipher.doFinal(ct), Charsets.UTF_8)
        } catch (_: Throwable) { null }
    }
}
