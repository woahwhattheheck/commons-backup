package com.local.deviceagent

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * JVM unit tests for MechanismRouter.mechanismFor — the pure failure-class → mechanism mapping (U2). recommend()
 * needs a Context/TaskHistory so it isn't unit-testable here, but the mapping is the part a taxonomy tweak can
 * silently break, so it's the part worth pinning. Key invariant: GROW is NEVER a failure-class response (self_grow
 * adds RAM — the wrong answer to an OOM/CAPACITY stop); GROW is reached only via the MetaFitness escalation.
 */
class MechanismRouterTest {

    @Test fun recognitionRoutesToGenesis() {
        assertEquals(MechanismRouter.GENESIS, MechanismRouter.mechanismFor("RECOGNITION"))
    }

    @Test fun perceptionNavigationTimingRouteToCalibrate() {
        assertEquals(MechanismRouter.CALIBRATE, MechanismRouter.mechanismFor("NAVIGATION"))
        assertEquals(MechanismRouter.CALIBRATE, MechanismRouter.mechanismFor("TIMING"))
        assertEquals(MechanismRouter.CALIBRATE, MechanismRouter.mechanismFor("VISIBILITY"))
        assertEquals(MechanismRouter.CALIBRATE, MechanismRouter.mechanismFor("INPUT"))
    }

    @Test fun capacityRoutesToCalibrateNotGrow() {
        // OOM/thermal/battery → re-tune the lean posture; GROW would add RAM and make it worse.
        assertEquals(MechanismRouter.CALIBRATE, MechanismRouter.mechanismFor("CAPACITY"))
    }

    @Test fun permissionAndUnknownRouteToNone() {
        assertEquals(MechanismRouter.NONE, MechanismRouter.mechanismFor("PERMISSION"))
        assertEquals(MechanismRouter.NONE, MechanismRouter.mechanismFor(""))
        assertEquals(MechanismRouter.NONE, MechanismRouter.mechanismFor("something-unclassified"))
    }

    @Test fun growIsNeverAFailureClassResponse() {
        // Guard the invariant across every class classifyFailure can emit.
        for (fc in listOf("CAPACITY", "PERMISSION", "NAVIGATION", "INPUT", "VISIBILITY", "TIMING", "RECOGNITION")) {
            assert(MechanismRouter.mechanismFor(fc) != MechanismRouter.GROW) { "$fc must not route to GROW" }
        }
    }
}
