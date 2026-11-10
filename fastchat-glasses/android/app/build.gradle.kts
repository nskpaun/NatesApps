import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val localProperties = Properties().apply {
    val file = rootDir.resolve("local.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}

android {
    namespace = "com.natesapps.fastchat"
    compileSdk = 36
    buildToolsVersion = "36.0.0"

    defaultConfig {
        applicationId = "com.natesapps.fastchat"
        minSdk = 31 // the Meta wearables toolkit needs Android 12
        targetSdk = 36
        versionCode = 1
        versionName = "0.1"

        // Meta Wearables Device Access Toolkit credentials. "0" is what Developer Mode expects;
        // put real values from the Wearables Developer Center in local.properties to ship.
        manifestPlaceholders["mwdat_application_id"] =
            localProperties.getProperty("mwdat_application_id", "0")
        manifestPlaceholders["mwdat_client_token"] =
            localProperties.getProperty("mwdat_client_token", "0")

        ndk { abiFilters += "arm64-v8a" }
        externalNativeBuild {
            cmake {
                // Always optimised: an unoptimised llama.cpp is many times slower, which would
                // make debug builds useless for judging reply speed.
                arguments += "-DCMAKE_BUILD_TYPE=Release"
            }
        }
    }
    ndkVersion = "28.2.13676358"
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.31.6"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }
    kotlin { jvmToolchain(21) }
    buildFeatures { compose = true }
    packaging { resources { excludes += "/META-INF/{AL2.0,LGPL2.1}" } }
}

dependencies {
    val bom = platform("androidx.compose:compose-bom:2026.05.01")
    implementation(bom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")

    // Meta Ray-Ban Display: session, display, d-pad inputs, and the simulated glasses.
    val mwdat = "1.0.1"
    implementation("com.meta.wearable:mwdat-core:$mwdat")
    implementation("com.meta.wearable:mwdat-display:$mwdat")
    implementation("com.meta.wearable:mwdat-inputs:$mwdat")
    implementation("com.meta.wearable:mwdat-mockdevice:$mwdat")

    // On-device speech: voice activity detection, speech to text and text to speech.
    implementation("com.github.k2-fsa.sherpa-onnx:sherpa-onnx:v2.0.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.11.0")
}
