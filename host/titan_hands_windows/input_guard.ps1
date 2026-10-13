function Get-TitanInputDecision {
    param(
        [string]$Mode,
        [string]$ControlId,
        [int]$TargetProcessId,
        [string]$TargetProcessName,
        [int]$ForegroundProcessId,
        [string]$FocusedControlId,
        [string]$Role,
        [bool]$Focusable,
        [bool]$HasValuePattern
    )

    $modeName = ([string]$Mode).Trim().ToLowerInvariant()
    $roleName = ([string]$Role).Trim().ToLowerInvariant()
    if (-not $ControlId) {
        return [pscustomobject]@{ ok = $false; route = ""; failure_reason = "INPUT_TARGET_REQUIRED"; message = "input requires a scoped control id" }
    }
    if ($TargetProcessId -le 0) {
        return [pscustomobject]@{ ok = $false; route = ""; failure_reason = "INPUT_OWNER_UNKNOWN"; message = "target control process is unavailable" }
    }
    if (-not $TargetProcessName) {
        return [pscustomobject]@{ ok = $false; route = ""; failure_reason = "INPUT_PROCESS_UNKNOWN"; message = "target control process name is unavailable" }
    }
    if ($TargetProcessName -match '(?i)(^|[._-])(codex|chatgpt)($|[._-])') {
        return [pscustomobject]@{ ok = $false; route = ""; failure_reason = "PROTECTED_INPUT_TARGET"; message = "text/key input is unavailable for protected Codex or ChatGPT controls" }
    }

    if ($modeName -in @("set_value", "type_text")) {
        if ($roleName -notin @("edit", "combobox", "spinner", "textbox")) {
            return [pscustomobject]@{ ok = $false; route = ""; failure_reason = "INPUT_ROLE_UNSUPPORTED"; message = "text input requires an Edit, ComboBox, Spinner, or TextBox control" }
        }
        if ($modeName -eq "set_value") {
            if (-not $HasValuePattern) {
                return [pscustomobject]@{ ok = $false; route = ""; failure_reason = "VALUE_PATTERN_UNAVAILABLE"; message = "set_value requires a supported per-control ValuePattern" }
            }
            return [pscustomobject]@{ ok = $true; route = "value_pattern"; failure_reason = ""; message = "" }
        }
        if ($HasValuePattern) {
            return [pscustomobject]@{ ok = $true; route = "value_pattern"; failure_reason = ""; message = "" }
        }
    } elseif ($modeName -ne "key") {
        return [pscustomobject]@{ ok = $false; route = ""; failure_reason = "INPUT_MODE_UNSUPPORTED"; message = "unsupported input mode" }
    }

    if (-not $Focusable) {
        return [pscustomobject]@{ ok = $false; route = ""; failure_reason = "INPUT_CONTROL_NOT_FOCUSABLE"; message = "native keyboard input requires a focusable control" }
    }
    if ($TargetProcessId -ne $ForegroundProcessId) {
        return [pscustomobject]@{ ok = $false; route = ""; failure_reason = "INPUT_FOREGROUND_MISMATCH"; message = "target process is not the foreground process" }
    }
    if ($ControlId -ne $FocusedControlId) {
        return [pscustomobject]@{ ok = $false; route = ""; failure_reason = "INPUT_FOCUS_MISMATCH"; message = "target control is not the focused control" }
    }
    return [pscustomobject]@{ ok = $true; route = "send_input"; failure_reason = ""; message = "" }
}

function Invoke-TitanBoundInput {
    param(
        [string]$Mode,
        [string]$ControlId,
        [int]$TargetProcessId,
        [string]$TargetProcessName,
        [int]$ForegroundProcessId,
        [string]$FocusedControlId,
        [string]$Role,
        [bool]$Focusable,
        [bool]$HasValuePattern,
        [string]$Text = "",
        [UInt16[]]$KeyCodes = @(),
        [scriptblock]$ValueWriter,
        [scriptblock]$KeyboardWriter
    )

    $decision = Get-TitanInputDecision `
        -Mode $Mode `
        -ControlId $ControlId `
        -TargetProcessId $TargetProcessId `
        -TargetProcessName $TargetProcessName `
        -ForegroundProcessId $ForegroundProcessId `
        -FocusedControlId $FocusedControlId `
        -Role $Role `
        -Focusable $Focusable `
        -HasValuePattern $HasValuePattern
    if (-not $decision.ok) {
        return [ordered]@{ ok = $false; kind = "failure"; failure_reason = $decision.failure_reason; message = $decision.message; emitted = $false }
    }
    if ($decision.route -eq "value_pattern") {
        if ($null -eq $ValueWriter) {
            return [ordered]@{ ok = $false; kind = "failure"; failure_reason = "VALUE_PATTERN_UNAVAILABLE"; message = "no per-control ValuePattern writer is available"; emitted = $false }
        }
        & $ValueWriter $Text
        return [ordered]@{ ok = $true; kind = "input_outcome"; route = $decision.route; emitted = $true }
    }
    if ($null -eq $KeyboardWriter) {
        return [ordered]@{ ok = $false; kind = "failure"; failure_reason = "INPUT_WRITER_UNAVAILABLE"; message = "native keyboard writer is unavailable"; emitted = $false }
    }
    if (([string]$Mode).Trim().ToLowerInvariant() -eq "key") {
        if ($KeyCodes.Count -gt 8) {
            return [ordered]@{ ok = $false; kind = "failure"; failure_reason = "INPUT_CHORD_TOO_LARGE"; message = "key chord exceeds the 8-key atomic batch limit"; emitted = $false }
        }
        & $KeyboardWriter $KeyCodes
    } else {
        if ($Text.Length -gt 32768) {
            return [ordered]@{ ok = $false; kind = "failure"; failure_reason = "INPUT_TOO_LARGE"; message = "text exceeds the 32768 UTF-16 code-unit atomic batch limit"; emitted = $false }
        }
        & $KeyboardWriter $Text
    }
    return [ordered]@{ ok = $true; kind = "input_outcome"; route = $decision.route; emitted = $true }
}



