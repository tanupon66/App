# ระบบบันทึกเวลาและคำนวณเงินเดือน — Android/Kivy

ไฟล์นี้เป็นเวอร์ชันเขียนใหม่สำหรับ Android เพราะ Tkinter/CustomTkinter ไม่สามารถแปลงเป็น APK ได้โดยตรง

## ฟังก์ชันที่มี
- บันทึกเวลาเข้า / ออกงานจากรหัสพนักงาน
- เข้างาน/ออกงานแบบอัตโนมัติ
- Login ผู้ดูแล
- เพิ่มพนักงาน
- ดูภาพรวมวันนี้
- แก้ไขเวลาเข้าออกพร้อมเหตุผลและ Audit log
- เพิ่มวันหยุด
- คำนวณเงินเดือน: วันทำงาน, ชั่วโมงปกติ, OT, นาทีสาย, หักสาย, รายได้สุทธิ
- Export CSV สำหรับ Attendance และ Payroll
- SQLite เก็บข้อมูลในเครื่องโทรศัพท์

## บัญชีเริ่มต้น
- Username: `admin`
- Password: `admin123`

## วิธี Build APK บน Linux
```bash
sudo apt update
sudo apt install -y python3-pip git zip unzip openjdk-17-jdk
pip install --user buildozer cython
cd attendance_android_app
buildozer android debug
```

ไฟล์ APK จะอยู่ที่:
```text
bin/thaiattendance-1.0-arm64-v8a_armeabi-v7a-debug.apk
```

## วิธี Build ด้วย GitHub Actions
1. สร้าง repo ใหม่ใน GitHub
2. อัปโหลดโฟลเดอร์นี้ทั้งหมด
3. ไปที่แท็บ Actions
4. รัน workflow ชื่อ `Build Android APK`
5. ดาวน์โหลดไฟล์ APK จาก Artifacts

## หมายเหตุสำคัญ
- เวอร์ชันนี้ใช้ Kivy ไม่ใช่ CustomTkinter
- Export เป็น CSV เพื่อให้ Android ใช้งานง่ายและเปิดด้วย Excel/Sheets ได้
- ถ้าต้องการ Export เป็น XLSX จริง สามารถเพิ่ม `openpyxl` ได้ แต่ไฟล์ APK จะใหญ่ขึ้น
