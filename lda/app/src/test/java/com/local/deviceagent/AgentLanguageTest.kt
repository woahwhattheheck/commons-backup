package com.local.deviceagent

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JVM unit tests for AgentLanguage — the compact action/perception codec (docs/AGENT_LANGUAGE.md). A codec
 * bug here ships a WRONG action, not a crash, so it's exactly the kind of silent regression a host test
 * catches. We assert by PARSING decodeAction's JSON (never string-equality on the serialization) so a
 * cosmetic key-order change doesn't fail a correct decode. The key contracts under test:
 *   - correct-or-abstain: a natural word or an unknown code returns null (the caller keeps the JSON path),
 *   - a real code decodes to the canonical {"action":...} JSON with the right args,
 *   - a message PAYLOAD keeps its case (never lowercased — the owner wants it sent verbatim).
 */
class AgentLanguageTest {

    private fun decode(raw: String): JSONObject? = AgentLanguage.decodeAction(raw)?.let { JSONObject(it) }

    @Test fun clickCodeCarriesId() {
        val o = decode("cl5")!!
        assertEquals("click", o.getString("action"))
        assertEquals(5, o.getInt("id"))
    }

    @Test fun bareClickHasNoId() {
        // A bare "cl" is still a valid click; the executor's salvage handles the missing id like malformed JSON.
        val o = decode("cl")!!
        assertEquals("click", o.getString("action"))
        assertFalse(o.has("id"))
    }

    @Test fun naturalWordIsNotMistakenForACode() {
        // "click id 5" starts with "cl" but the next char is a letter → a WORD, not the code → abstain.
        assertNull(AgentLanguage.decodeAction("click id 5"))
    }

    @Test fun unknownCodeAbstains() {
        assertNull(AgentLanguage.decodeAction("zzz"))
        assertNull(AgentLanguage.decodeAction("q"))
    }

    @Test fun setTextKeepsIdAndPayloadCase() {
        val o = decode("st5:Hello World")!!
        assertEquals("set_text", o.getString("action"))
        assertEquals(5, o.getInt("id"))
        assertEquals("Hello World", o.getString("text"))   // case preserved — never lowercased
    }

    @Test fun findTakesWholeLabelIncludingNumeric() {
        // find/search/reveal are text-only: a leading digit is part of the LABEL, not an id (the old bug
        // mis-read it as an id and dropped the text).
        val o = decode("fd 2024")!!
        assertEquals("find", o.getString("action"))
        assertEquals("2024", o.getString("text"))
    }

    @Test fun peekZoneMapsToRegion() {
        val o = decode("pk9")!!
        assertEquals("peek", o.getString("action"))
        assertEquals("top-right", o.getString("region"))
    }

    @Test fun scrollDefaultsDownAndHonorsDirection() {
        assertEquals("down", decode("sc")!!.getString("direction"))
        assertEquals("up", decode("sc up")!!.getString("direction"))
    }

    @Test fun scrollUnknownDirectionAbstains() {
        // Never silently scroll the WRONG way — an unrecognized direction rides as JSON instead.
        assertNull(AgentLanguage.decodeAction("sc sideways"))
    }

    @Test fun openAppNameRequired() {
        assertEquals("Chrome", decode("oa Chrome")!!.getString("name"))
        assertNull(AgentLanguage.decodeAction("oa"))   // no name → abstain
    }

    @Test fun noArgVerbsDecodeCleanly() {
        assertEquals("back", decode("bk")!!.getString("action"))
        assertEquals("home", decode("hm")!!.getString("action"))
        assertEquals("done", decode("dn")!!.getString("action"))
    }

    @Test fun quotedCodeIsUnwrapped() {
        // A model that wraps the code in quotes still decodes (the executor sees these forms in the wild).
        val o = decode("\"cl3\"")!!
        assertEquals("click", o.getString("action"))
        assertEquals(3, o.getInt("id"))
    }

    @Test fun everyCodeRoundTripsToItsVerb() {
        // The two maps must stay inverses — a dropped/duplicated code silently loses a verb.
        assertEquals(AgentLanguage.VERB_TO_CODE.size, AgentLanguage.CODE_TO_VERB.size)
        for ((verb, code) in AgentLanguage.VERB_TO_CODE) {
            assertEquals(verb, AgentLanguage.CODE_TO_VERB[code])
        }
    }

    @Test fun roleAndStateCharsMatchTheLegend() {
        assertEquals("f", AgentLanguage.roleChar("field"))
        assertEquals("", AgentLanguage.roleChar(""))              // plain tap = default, no weight
        assertEquals("-", AgentLanguage.stateChar(              // disabled outranks everything
            enabled = false, selected = true, focused = true, editable = true, checkable = true, checked = true))
        assertEquals("*", AgentLanguage.stateChar(              // checked checkable
            enabled = true, selected = false, focused = false, editable = false, checkable = true, checked = true))
        assertEquals("", AgentLanguage.stateChar(               // normal
            enabled = true, selected = false, focused = false, editable = false, checkable = false, checked = false))
    }

    @Test fun renderItemComposesIdRoleStateAndIconLabel() {
        assertEquals("5f^", AgentLanguage.renderItem(5, "f", "^", null))
        assertTrue(AgentLanguage.renderItem(7, "", "", "Send").endsWith("\"Send\""))
    }
}
