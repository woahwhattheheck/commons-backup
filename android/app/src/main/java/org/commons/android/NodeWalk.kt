package org.commons.android

data class Bounds(val x: Int, val y: Int, val width: Int, val height: Int) {
    val centerX: Int get() = x + width / 2
    val centerY: Int get() = y + height / 2
}

data class RawNode(
    val className: String = "",
    val text: String = "",
    val contentDescription: String = "",
    val viewId: String = "",
    val packageName: String = "",
    val bounds: Bounds = Bounds(0, 0, 0, 0),
    val enabled: Boolean = true,
    val focusable: Boolean = false,
    val focused: Boolean = false,
    val selected: Boolean = false,
    val checked: Boolean = false,
    val checkable: Boolean = false,
    val clickable: Boolean = false,
    val longClickable: Boolean = false,
    val scrollable: Boolean = false,
    val editable: Boolean = false,
    val password: Boolean = false,
    val children: List<RawNode> = emptyList(),
)

data class SemanticNode(
    val id: String,
    val parent: String,
    val role: String,
    val name: String,
    val automationId: String,
    val className: String,
    val packageName: String,
    val contentDescription: String,
    val value: String,
    val bounds: Bounds,
    val states: List<String>,
    val actions: List<String>,
)

object NodeWalk {
    fun role(className: String): String {
        val leaf = className.substringAfterLast('.', className)
        return when (leaf) {
            "Button", "ImageButton" -> "Button"
            "EditText" -> "TextBox"
            "TextView" -> "Text"
            "CheckBox" -> "CheckBox"
            "RadioButton" -> "RadioButton"
            "Switch" -> "Switch"
            "ImageView" -> "Image"
            "ListView", "RecyclerView" -> "List"
            "ScrollView", "NestedScrollView" -> "Pane"
            "WebView" -> "Document"
            else -> leaf.ifBlank { "Node" }
        }
    }

    fun nodeId(serial: String, path: String, viewId: String, className: String): String {
        val identity = listOf(serial, path, viewId, className).joinToString("|")
        return "a_" + sha256Hex(identity).take(20)
    }

    fun walk(root: RawNode, serial: String = "phone", maxNodes: Int = 400): List<SemanticNode> {
        val nodes = ArrayList<SemanticNode>()
        fun visit(node: RawNode, path: String, parent: String) {
            if (nodes.size >= maxNodes) return
            val id = nodeId(serial, path, node.viewId, node.className)
            val role = role(node.className)
            val states = mutableListOf<String>()
            if (node.enabled) states += "enabled"
            if (node.focusable) states += "focusable"
            if (node.focused) states += "focused"
            if (node.selected) states += "selected"
            if (node.checked) states += "checked"
            if (node.checkable) states += "checkable"
            if (node.clickable) states += "clickable"
            if (node.longClickable) states += "long-clickable"
            if (node.scrollable) states += "scrollable"
            if (node.password) states += "password"
            if (node.editable) states += "editable"
            val actions = linkedSetOf<String>()
            if (node.clickable) {
                actions += "click"
                actions += "invoke"
            }
            if (node.focusable) actions += "focus"
            if (node.checkable) actions += "toggle"
            if (role == "TextBox" || node.editable) {
                actions += "set_value"
                actions += "type_text"
            }
            if (node.scrollable) actions += "scroll"
            val name = node.text.ifBlank { node.contentDescription.ifBlank { node.viewId.substringAfterLast('/') } }
            nodes += SemanticNode(
                id = id,
                parent = parent,
                role = role,
                name = name,
                automationId = node.viewId,
                className = node.className,
                packageName = node.packageName,
                contentDescription = node.contentDescription,
                value = node.text,
                bounds = node.bounds,
                states = states.sorted(),
                actions = actions.sorted(),
            )
            node.children.forEachIndexed { index, child ->
                visit(child, "$path.$index", id)
            }
        }
        visit(root, "0", "")
        return nodes
    }
}
