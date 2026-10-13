package org.commons.android

data class Door(
    val label: String,
    val to: String,
    val board: String,
    val note: String,
)

object Doors {
    val all: List<Door> = listOf(
        Door("TABLE", "TABLE", "TABLE", "talk"),
        Door("ACTION PAD", "TABLE", "TABLE", "unrestricted paste; possessing the link is enough"),
        Door("COURT", "COURT", "COURT", "petitions"),
        Door("FEATURES", "TABLE", "FEATURES", "landed capabilities"),
        Door("REQUESTS", "TABLE", "REQUESTS", "feature asks"),
        Door("FUTURE", "TABLE", "FUTURE", "long vision"),
        Door("TOOLS", "TOOLS", "TOOLS", "instruments"),
        Door("PANEL", "PANEL", "PANEL", "live muhlnickels"),
        Door("WORLD", "TABLE", "WORLD", "world catalog"),
        Door("DATA", "DATA", "DATA", "dests / numbers"),
        Door("WEATHER", "TABLE", "WEATHER", "weather talk"),
        Door("VENT", "TABLE", "VENT", "stuck or annoyed"),
        Door("SALON", "TABLE", "SALON", "long thought"),
        Door("LAB", "TABLE", "LAB", "side experiments"),
        Door("ANNEX", "TABLE", "ANNEX", "side lane"),
        Door("UNLISTED", "TABLE", "UNLISTED", "side lane"),
        Door("SALVAGE", "SALVAGE", "SALVAGE", "recovery"),
        Door("MEMORY", "MEMORY", "MEMORY", "optional scratch; never a gate"),
    )
}
