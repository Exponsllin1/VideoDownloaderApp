[app]
title = 视频下载器
package.name = videodownloader
package.domain = org.example

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt

version = 0.1
requirements = python3==3.7.9,kivy==2.0.0,requests,urllib3,chardet,idna,certifi,android

orientation = portrait
osx.python = 3.7
osx.kivy = 2.0.0

fullscreen = 0

[buildozer]
log_level = 2
warn_on_root = 1

[app]
# Android 特定配置
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 28
android.minapi = 21
android.sdk = 28
android.ndk = 19c
android.ndk_api = 21
android.gradle_download = False
android.allow_backup = True
android.accept_sdk_license = True

# 使用稳定的工具版本
android.sdk_manager_tools_version = 26.1.1
android.gradle_tools_version = 3.5.0
android.build_tools_version = 28.0.3
android.compile_sdk_version = 28
android.target_sdk_version = 28

# Python 配置
python.version = 3.7.9
python.legacy_version = true

# 入口点
presplash.filename = %(source.dir)s/presplash.png
icon.filename = %(source.dir)s/icon.png

# 构建优化
android.arch = armeabi-v7a
p4a.branch = develop

# 修复可能的构建问题
android.add_src =
android.add_res =
android.add_manifest =
android.add_aars =
android.add_jars =
android.add_java_src =