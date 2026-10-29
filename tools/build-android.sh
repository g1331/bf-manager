#!/usr/bin/env bash
# 构建安卓壳 App（apps/android），签好名放到站点的下载目录
#
# 壳只是个全屏 WebView，网站更新不用重新出包；只有改了壳本身（图标、链接处理等）才需要跑这个脚本，
# 并记得先把 app/build.gradle.kts 里的 versionCode 加一，否则装过旧版的手机不会覆盖升级。
#
# 签名密钥只存在生产机的 secrets 目录，不进仓库；密钥丢了就再也发不了能覆盖安装的新版，务必另行备份。
# 本机不装 JDK / 安卓 SDK，在 Docker 里构建。
#
# 用法：
#   bash tools/build-android.sh                                  # 默认密钥目录 /srv/bf-manager/secrets
#   BFM_SECRETS_DIR=/path/to/secrets bash tools/build-android.sh

set -euo pipefail

cd "$(cd "$(dirname "$0")/.." && pwd)"

SECRETS_DIR="${BFM_SECRETS_DIR:-/srv/bf-manager/secrets}"
IMAGE="ghcr.io/cirruslabs/android-sdk:35"
OUTPUT="apps/web/public/download/bf-manager.apk"

for f in android-release.jks android_keystore_password; do
  [[ -f "$SECRETS_DIR/$f" ]] || { echo "缺少 $SECRETS_DIR/$f" >&2; exit 1; }
done

docker run --rm \
  -v "$PWD/apps/android":/src \
  -v bfm-gradle-cache:/root/.gradle \
  -v "$SECRETS_DIR":/secrets:ro \
  -w /src "$IMAGE" bash -c '
    set -euo pipefail
    export BFM_KEYSTORE=/secrets/android-release.jks BFM_KEY_ALIAS=bfm
    BFM_KEYSTORE_PASSWORD="$(cat /secrets/android_keystore_password)"
    export BFM_KEYSTORE_PASSWORD BFM_KEY_PASSWORD="$BFM_KEYSTORE_PASSWORD"
    ./gradlew --no-daemon -q clean assembleRelease
    "$ANDROID_HOME"/build-tools/35.0.0/apksigner verify app/build/outputs/apk/release/app-release.apk
  '

mkdir -p "$(dirname "$OUTPUT")"
cp apps/android/app/build/outputs/apk/release/app-release.apk "$OUTPUT"
echo "已输出 $OUTPUT（$(du -h "$OUTPUT" | cut -f1)）"
