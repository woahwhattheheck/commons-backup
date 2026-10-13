plugins {
    id("com.android.application")
}

val revenueCatKey = providers.gradleProperty("PROOFPOCKET_REVENUECAT_PUBLIC_SDK_KEY").orElse("")

android {
    namespace = "com.tokenjunkielabs.proofpocket"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.tokenjunkielabs.proofpocket"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "REVENUECAT_PUBLIC_SDK_KEY", "\"${revenueCatKey.get()}\"")
        buildConfigField("String", "REVENUECAT_ENTITLEMENT_ID", "\"pro\"")
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
}

dependencies {
    implementation("com.revenuecat.purchases:purchases:10.15.1")
}
