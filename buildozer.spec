[app]

# (str) Title of your application
title = Suri Portal

# (str) Package name
package.name = portalaluno

# (str) Package domain
package.domain = org.fractal

# (str) Source code directory
source.dir = .

# (str) Application version
version = 0.2
android.numeric_version = 10262

# (list) Source file extensions
source.include_exts = py,png,jpg,kv,atlas
source.exclude_patterns = test_api_client.py,__pycache__/*
source.exclude_dirs = tools

# (list) Python requirements
requirements = python3,kivy==2.3.1,requests,pyjnius,certifi,urllib3,charset_normalizer,idna

# (str) Orientation
orientation = portrait

# (bool) Fullscreen
fullscreen = 0

# (list) Android permissions
android.permissions = INTERNET
android.extra_manifest_application_xml = android/extra_manifest_application_arguments.xml
android.add_resources = android/res
android.gradle_dependencies = androidx.core:core:1.13.1
android.enable_androidx = True

# Android target/minimum API
android.api = 36
android.minapi = 26

# Use the current python-for-android development branch.
# This is important for the newer Python/pip environment seen in the failed build.
p4a.branch = develop

# Let python-for-android/Buildozer manage the NDK instead of hard-coding
# the runner's installed NDK path.
android.ndk = 28c

# Architectures
android.archs = arm64-v8a,armeabi-v7a

# Android backup
android.allow_backup = True


[buildozer]

# Buildozer log verbosity
log_level = 2

# Allow execution as root in CI if necessary
warn_on_root = 1
