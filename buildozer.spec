[app]
title = Portal do Aluno
package.name = portalaluno
package.domain = org.fractal
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1

requirements = python3,kivy==2.3.1,requests,plyer,pyjnius,certifi,urllib3,charset_normalizer,idna

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 34
android.minapi = 26
android.ndk_path = /usr/local/lib/android/sdk/ndk/27.3.13750724
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
