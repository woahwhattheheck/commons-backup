package com.tokenjunkielabs.proofpocket.core

data class EntitlementDecision(val pro: Boolean, val reason: String)

object EntitlementPolicy {
    fun evaluate(configured: Boolean, callbackSucceeded: Boolean, entitlementActive: Boolean): EntitlementDecision {
        if (!configured) return EntitlementDecision(false, "RevenueCat public SDK key is not configured")
        if (!callbackSucceeded) return EntitlementDecision(false, "RevenueCat entitlement state was not observed successfully")
        if (!entitlementActive) return EntitlementDecision(false, "RevenueCat 'pro' entitlement is inactive")
        return EntitlementDecision(true, "RevenueCat 'pro' entitlement observed active")
    }
}
