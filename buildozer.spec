[app]
title = Thai Attendance Payroll
package.name = thaiattendance
package.domain = org.example
source.dir = .
source.include_exts = py,png,jpg,kv,ttf,sqlite3,csv
version = 1.0
requirements = python3,kivy
orientation = portrait
fullscreen = 0
android.permissions = WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 35
android.build_tools_version = 35.0.0
android.sdk_path = /usr/local/lib/android/sdk
android.minapi = 23
android.archs = arm64-v8a,armeabi-v7a

[buildozer]
log_level = 2
warn_on_root = 1
