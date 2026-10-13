package com.tokenjunkielabs.proofpocket.billing

import android.app.Activity
import android.content.Context
import com.revenuecat.purchases.Purchases
import com.revenuecat.purchases.PurchasesConfiguration
import com.revenuecat.purchases.getCustomerInfoWith
import com.revenuecat.purchases.getOfferingsWith
import com.revenuecat.purchases.models.StoreTransaction
import com.revenuecat.purchases.purchaseWith
import com.revenuecat.purchases.restorePurchasesWith
import com.revenuecat.purchases.PurchaseParams
import com.tokenjunkielabs.proofpocket.BuildConfig
import com.tokenjunkielabs.proofpocket.core.EntitlementPolicy

sealed class BillingState {
    data object NotConfigured : BillingState()
    data object Loading : BillingState()
    data class Ready(val pro: Boolean, val message: String) : BillingState()
    data class Error(val message: String) : BillingState()
}

class RevenueCatGate(private val context: Context) {
    private val sdkKey = BuildConfig.REVENUECAT_PUBLIC_SDK_KEY.trim()
    private var configured = false
    var state: BillingState = BillingState.NotConfigured
        private set

    fun configure(onState: (BillingState) -> Unit) {
        if (sdkKey.isBlank()) {
            state = BillingState.NotConfigured
            onState(state)
            return
        }
        if (!configured) {
            Purchases.configure(PurchasesConfiguration.Builder(context, sdkKey).build())
            configured = true
        }
        refresh(onState)
    }

    fun refresh(onState: (BillingState) -> Unit) {
        if (!configured) {
            state = BillingState.NotConfigured
            onState(state)
            return
        }
        state = BillingState.Loading
        onState(state)
        Purchases.sharedInstance.getCustomerInfoWith(
            onError = { error ->
                val decision = EntitlementPolicy.evaluate(true, false, false)
                state = BillingState.Error("${decision.reason}: ${error.message}")
                onState(state)
            },
            onSuccess = { info ->
                val active = info.entitlements[BuildConfig.REVENUECAT_ENTITLEMENT_ID]?.isActive == true
                val decision = EntitlementPolicy.evaluate(true, true, active)
                state = BillingState.Ready(decision.pro, decision.reason)
                onState(state)
            },
        )
    }

    fun purchaseCurrent(activity: Activity, onState: (BillingState) -> Unit) {
        if (!configured) {
            state = BillingState.NotConfigured
            onState(state)
            return
        }
        state = BillingState.Loading
        onState(state)
        Purchases.sharedInstance.getOfferingsWith(
            onError = { error ->
                state = BillingState.Error("Unable to load RevenueCat offering: ${error.message}")
                onState(state)
            },
            onSuccess = { offerings ->
                val packageToBuy = offerings.current?.availablePackages?.firstOrNull()
                if (packageToBuy == null) {
                    state = BillingState.Error("No current RevenueCat package is configured")
                    onState(state)
                } else {
                    Purchases.sharedInstance.purchaseWith(
                        PurchaseParams.Builder(activity, packageToBuy).build(),
                        onError = { error, cancelled ->
                            state = BillingState.Error(if (cancelled) "Purchase cancelled" else "Purchase failed: ${error.message}")
                            onState(state)
                        },
                        onSuccess = { _: StoreTransaction, info ->
                            val active = info.entitlements[BuildConfig.REVENUECAT_ENTITLEMENT_ID]?.isActive == true
                            val decision = EntitlementPolicy.evaluate(true, true, active)
                            state = BillingState.Ready(decision.pro, decision.reason)
                            onState(state)
                        },
                    )
                }
            },
        )
    }

    fun restore(onState: (BillingState) -> Unit) {
        if (!configured) {
            state = BillingState.NotConfigured
            onState(state)
            return
        }
        state = BillingState.Loading
        onState(state)
        Purchases.sharedInstance.restorePurchasesWith(
            onError = { error ->
                state = BillingState.Error("Restore failed: ${error.message}")
                onState(state)
            },
            onSuccess = { info ->
                val active = info.entitlements[BuildConfig.REVENUECAT_ENTITLEMENT_ID]?.isActive == true
                val decision = EntitlementPolicy.evaluate(true, true, active)
                state = BillingState.Ready(decision.pro, decision.reason)
                onState(state)
            },
        )
    }

    fun isPro(): Boolean = (state as? BillingState.Ready)?.pro == true
}
