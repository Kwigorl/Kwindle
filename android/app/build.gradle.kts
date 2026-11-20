import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.chaquo.python")
}

// ABI compilées : arm64 pour le téléphone, x86_64 pour l'émulateur des tests (-Pabis=x86_64)
val abis = (findProperty("abis") as String? ?: "arm64-v8a").split(",").map { it.trim() }


android {
    namespace = "fr.kwigorl.kwindle"
    compileSdk = 35

    defaultConfig {
        applicationId = "fr.kwigorl.kwindle"
        minSdk = 29
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
        ndk {
            // le Poco F7 (et tous les téléphones récents) sont en arm64 ;
            // les tests sur émulateur passent -Pabis=x86_64
            abiFilters += abis
        }
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    // Clé de signature de l'appli : toujours la même, pour pouvoir installer
    // les nouvelles versions par-dessus l'ancienne.
    signingConfigs {
        create("kwindle") {
            storeFile = file("kwindle.jks")
            storePassword = "kwindle-nico"
            keyAlias = "kwindle"
            keyPassword = "kwindle-nico"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("kwindle")
        }
        debug {
            signingConfig = signingConfigs.getByName("kwindle")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

chaquopy {
    defaultConfig {
        version = "3.13"
        pip {
            install("lxml")
            install("pillow")
            install("mobi")
            install("certifi")
        }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.08.00")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.9.0")
    implementation("androidx.core:core-ktx:1.16.0")

    // torrents
    implementation("org.libtorrent4j:libtorrent4j:2.1.0-39")
    if ("arm64-v8a" in abis) implementation("org.libtorrent4j:libtorrent4j-android-arm64:2.1.0-39")
    if ("x86_64" in abis) implementation("org.libtorrent4j:libtorrent4j-android-x86_64:2.1.0-39")

    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test:core:1.6.1")
}
