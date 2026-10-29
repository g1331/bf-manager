plugins {
    id("com.android.application")
}

// 正式签名从环境变量读取，密钥文件不进仓库；没配时 release 包不签名，只能装 debug 包测试
val keystorePath: String? = System.getenv("BFM_KEYSTORE")

android {
    namespace = "com.umrbotech.bfm"
    compileSdk = 35
    buildToolsVersion = "35.0.0"

    defaultConfig {
        applicationId = "com.umrbotech.bfm"
        minSdk = 24
        // 停在 34：35 起 Android 15 强制网页铺到状态栏底下，站点没按 App 内嵌处理状态栏留白
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
    }

    signingConfigs {
        if (keystorePath != null) {
            create("release") {
                storeFile = file(keystorePath)
                storePassword = System.getenv("BFM_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("BFM_KEY_ALIAS")
                keyPassword = System.getenv("BFM_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
            signingConfig = signingConfigs.findByName("release")
        }
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
