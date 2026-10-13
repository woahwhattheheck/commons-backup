package com.local.deviceagent

import org.json.JSONObject

/**
 * AGENT LANGUAGE (LANG) — the single source of truth for the compact perception + action codec.
 * See docs/AGENT_LANGUAGE.md. The owner's spec: each PERCEIVED ITEM and each ACTION rendered as tiny as
 * possible, taught by the operators, so per-step prompt tokens drop while agent-driven success holds.
 *
 * The BINDING constraint is TOKENS, not characters (the model pays in tokens; a glyph like `^` can be its
 * own token). Target ≤2 tokens/item on perception (the multiplied win). Actions are one-per-step (~12 tok),
 * so they are kept compact + reliably-emitted + cleanly-decoded but NOT hard-capped. There is NO decode-time
 * grammar in this LiteRT-LM build (verified: SamplerConfig = topK/topP/temperature only), so the codec is
 * SOFT: TAUGHT (operator clauses + the legends below) and PARSED (decodeAction accepts codes ALONGSIDE
 * today's JSON — never a hard switch, so a model still emitting JSON keeps working).
 *
 * Pure Kotlin (no Android deps) so it is unit-testable and the service just feeds it primitives.
 */
object AgentLanguage {

    // ---- PERCEPTION CODEC (input) --------------------------------------------------------------------
    // A rendered item is `⟨id⟩⟨role?⟩⟨state?⟩` + (icon-only) a short "label". The id is the EXACT tap handle
    // (the [N] index the executor resolves via currentNodes[N]) — never altered. role/state are 1 char each;
    // a plain tappable button is the DEFAULT (no role char), matching describe()'s token-light choice. The
    // LABEL is dropped for text-bearing elements (the screenshot pixels carry "Send"); it is KEPT only for
    // an icon-only element (contentDescription, no visible on-screen text — the pixels don't carry it).

    /** Map describe()'s role word to a 1-char code. "" (plain button/tap, the common case) stays "". */
    fun roleChar(roleWord: String): String = when (roleWord) {
        "field" -> "f"
        "toggle" -> "t"
        "tab" -> "x"
        "" -> ""            // plain tappable control — the default, no weight
        else -> "v"          // a rare non-clickable view / other class
    }

    /** One state char (priority: disabled > selected > focused > checkable), "" when normal. Mirrors the
     *  describe() STATE tags [disabled]/[selected]/[focused]/[checked]/[unchecked] the model relies on. */
    fun stateChar(enabled: Boolean, selected: Boolean, focused: Boolean, editable: Boolean,
                  checkable: Boolean, checked: Boolean): String = when {
        !enabled -> "-"
        selected -> "="
        focused && editable -> "^"
        checkable -> if (checked) "*" else "o"
        else -> ""
    }

    /** Render ONE perceived item. [iconLabel] non-null only for an icon-only element (kept short). */
    fun renderItem(id: Int, roleChar: String, stateChar: String, iconLabel: String?): String =
        "$id$roleChar$stateChar" + (iconLabel?.let { "\"$it\"" } ?: "")

    /** The perception LEGEND — one terse line in the STABLE prefix (warm KV, amortized) that TEACHES the
     *  reading. Kept tiny; the model already knows [N]=tap. */
    fun perceptionLegend(): String =
        "ITEMS (compact): each line is an id you can tap. After the id: f=field t=toggle x=tab (plain tap has none); " +
        "-=disabled ==selected ^=focused *=on o=off; \"name\" = an icon with no visible text. No name → read the " +
        "label off the screenshot badge with that number."

    // ---- ACTION CODEC (output) -----------------------------------------------------------------------
    // Each verb → a short (mostly 2-char) mnemonic code. Args ride after: an id/number (`cl5`), a 1-char
    // zone for regions (`pk9` = peek numpad-zone 9 = top-right), or an exempt content PAYLOAD after ':'
    // (`st5:your message` — the message is data the owner wants sent, never compressed). Decode ACCEPTS
    // codes alongside JSON; it never replaces the forgiving JSON salvage (that stays the floor).

    /** verb → code. Canonical executor verbs (ActionAccessibilityService.performActionJson) + the
     *  orchestrator-handled reply/ocr/armed. Chosen for memorability + no collisions. */
    val VERB_TO_CODE: Map<String, String> = linkedMapOf(
        "click" to "cl", "set_text" to "st", "clear" to "cr", "find" to "fd", "reveal" to "rv",
        "peek" to "pk", "zoom" to "zm", "zoom_out" to "zo", "next_page" to "np", "prev_page" to "pp",
        "scroll" to "sc", "swipe" to "sw", "tap_xy" to "xy", "aim" to "am", "tap_grid" to "tg",
        "tap_near" to "tn", "tap_sequence" to "tq", "long_press" to "lp", "draw" to "dw", "sketch" to "sk",
        "enter" to "en", "send" to "sd", "reply" to "rp", "app_drawer" to "ad", "open_app" to "oa",
        "back" to "bk", "home" to "hm", "recent_apps" to "ra", "notifications" to "nf", "quick_settings" to "qs",
        "split_screen" to "sp", "search" to "se", "copy" to "cp", "paste" to "ps", "read_clipboard" to "rc",
        "capture" to "ct", "ocr" to "oc", "get_text" to "gt", "assert" to "at", "armed" to "ar",
        "save_note" to "sn", "save_login" to "sv", "connected_devices" to "cd", "wait" to "wt", "ask" to "ak",
        "done" to "dn", "do" to "do", "help" to "hp", "dial" to "dl", "sms" to "sm", "set_alarm" to "sa",
        "navigate" to "nv", "web" to "wb", "batch" to "bt", "drag" to "dg"
    )
    val CODE_TO_VERB: Map<String, String> = VERB_TO_CODE.entries.associate { (v, c) -> c to v }

    // The verb classes the decoder handles CLEANLY. A code whose verb is in none of these returns null, so
    // the caller keeps today's JSON path — decode is correct-or-abstain, never a degraded action.
    private val NO_ARG = setOf("back", "home", "done", "enter", "send", "reply", "zoom_out", "app_drawer",
        "recent_apps", "notifications", "quick_settings", "split_screen", "read_clipboard", "capture", "ocr",
        "wait", "next_page", "prev_page", "connected_devices")
    /** ARG is a numeric element id (`cl5` → id 5). */
    private val ID_ARG = setOf("click", "clear", "long_press", "copy", "paste", "get_text")
    /** ARG is a 3×3 zone digit 1-9 (numpad layout: 1=bottom-left … 9=top-right). */
    private val ZONE_ARG = setOf("peek", "zoom")
    /** Optional leading id then a text PAYLOAD after ':' (`st5:msg`, `se:query`). */
    private val TEXT_ARG = setOf("set_text", "search", "find", "reveal")
    private val ZONE = mapOf(
        '1' to "bottom-left", '2' to "bottom", '3' to "bottom-right", '4' to "left", '5' to "center",
        '6' to "right", '7' to "top-left", '8' to "top", '9' to "top-right")

    /** Decode a bare LANG action code into canonical action JSON, or null if [raw] is not a clean code
     *  (then the caller keeps today's JSON/salvage path). STRICT so a natural word ("click id 5") is NOT
     *  mistaken for the code "cl": the char right after the code must be a non-letter (digit / ':' / space /
     *  end). Case is preserved for the PAYLOAD (a message the owner wants sent must not be lowercased). Only
     *  the common verb classes decode; a code for a complex verb (assert/armed/batch/draw/…) returns null so
     *  it rides as JSON — decode is correct-or-abstain. */
    fun decodeAction(raw: String): String? {
        val trimmed = raw.trim().trim('"', '\'', '`')
        if (trimmed.length < 2) return null
        val lower = trimmed.lowercase()
        val code = when {
            trimmed.length >= 3 && CODE_TO_VERB.containsKey(lower.substring(0, 3)) -> lower.substring(0, 3)
            CODE_TO_VERB.containsKey(lower.substring(0, 2)) -> lower.substring(0, 2)
            else -> return null
        }
        val verb = CODE_TO_VERB[code] ?: return null
        val rest = trimmed.substring(code.length)               // original case, for payloads
        if (rest.isNotEmpty() && rest[0].isLetter()) return null // "click…" is a word, not the code "cl"
        val r = rest.trim()
        val o = JSONObject().put("action", verb)
        when {
            verb == "scroll" -> {
                // `sc` alone = scroll down (common). Honor a trailing direction word (`sc up`) + optional pane
                // id; an unknown arg abstains → rides as JSON, so we never silently scroll the WRONG way.
                val word = r.lowercase().takeWhile { it.isLetter() }
                val dir = when (word) { "", "down" -> "down"; "up" -> "up"; "left" -> "left"; "right" -> "right"; else -> return null }
                o.put("direction", dir)
                r.dropWhile { it.isLetter() }.trim().takeWhile { it.isDigit() }.toIntOrNull()?.let { o.put("id", it) }
            }
            verb == "open_app" -> { if (r.isBlank()) return null; o.put("name", r.removePrefix(":").trim()) }
            verb in NO_ARG -> {}
            verb in ID_ARG -> r.takeWhile { it.isDigit() }.toIntOrNull()?.let { o.put("id", it) }
            verb in ZONE_ARG -> ZONE[r.firstOrNull()]?.let { o.put("region", it) }
            verb in TEXT_ARG -> {
                // Only set_text carries an id BEFORE the text (`st5:msg`); find/search/reveal are text-only, so
                // a colon-less arg is the WHOLE label/query — including a numeric one (`fd 2024`). The old code
                // mis-read a leading digit as an id and dropped the text (a degraded action instead of the label).
                val hasId = verb == "set_text"
                val payload = when {
                    r.contains(':') -> r.substringAfter(':').trim()
                    hasId && r.firstOrNull()?.isDigit() == true -> ""   // "st5" = field 5, text still to come
                    else -> r                                           // whole arg is the label/query (incl. numeric)
                }
                if (hasId) r.substringBefore(':').takeWhile { it.isDigit() }.toIntOrNull()?.let { o.put("id", it) }
                if (payload.isNotBlank()) o.put("text", payload)
            }
            else -> return null                                  // complex verb → let it ride as JSON
        }
        // scroll adds "down" but the raw was just "sc"; NO_ARG/scroll are complete. arg verbs with a missing
        // arg (e.g. a bare "cl") still return {"action":"click"} — the executor's salvage handles that exactly
        // as it handles a malformed JSON click, so no new failure mode is introduced.
        return o.toString()
    }

    /** The action LEGEND — a terse code list for the STABLE prefix, so the model can emit codes. Only the
     *  common verbs are spelled out; the rest are reachable because the decoder + JSON both still work. */
    fun actionLegend(): String =
        "ACTION CODES (emit a short code, e.g. cl5 = click id 5): cl click·st set_text(id:text)·pk peek(1-9 zone)·" +
        "sc scroll·bk back·hm home·oa open_app·ad app_drawer·fd find(:label)·se search(:q)·sd send·rp reply·" +
        "gt get_text·oc ocr·cp copy·ps paste·dn done·wt wait. Numbers = an id; a message rides after ':'."
}
