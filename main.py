# -*- coding: utf-8 -*-
"""
Android-ready Kivy rewrite of a Thai attendance/payroll system.
Default admin: admin / admin123
Build with Buildozer on Linux or GitHub Actions.
"""
from __future__ import annotations

import csv
import hashlib
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.textinput import TextInput

try:
    from android.storage import app_storage_path  # type: ignore
except Exception:  # desktop testing
    app_storage_path = None

Window.clearcolor = (0.06, 0.08, 0.16, 1)

PRIMARY = (0.12, 0.53, 0.90, 1)
SUCCESS = (0.26, 0.63, 0.28, 1)
WARNING = (0.98, 0.55, 0.00, 1)
DANGER = (0.90, 0.22, 0.20, 1)
CARD = (0.09, 0.13, 0.25, 1)
SURFACE = (0.06, 0.20, 0.38, 1)
WHITE = (1, 1, 1, 1)
MUTED = (0.75, 0.78, 0.85, 1)


def app_dir() -> Path:
    if app_storage_path:
        p = Path(app_storage_path())
    else:
        p = Path(__file__).resolve().parent / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            pass
    return None


def fmt_time(value: Optional[str]) -> str:
    dt = parse_dt(value)
    return dt.strftime("%H:%M") if dt else "—"


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


@dataclass
class Employee:
    id: int = 0
    employee_code: str = ""
    full_name: str = ""
    department: str = ""
    position: str = ""
    daily_rate: float = 0.0
    hourly_rate: float = 0.0
    ot_rate_multiplier: float = 1.5
    standard_start: str = "08:00"
    standard_end: str = "17:00"
    is_active: bool = True


@dataclass
class Holiday:
    id: int = 0
    holiday_date: str = ""
    description: str = ""
    is_paid: bool = True


class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(app_dir() / "attendance.sqlite3")
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init_db()

    def init_db(self):
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS admins(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS employees(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_code TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                department TEXT DEFAULT '',
                position TEXT DEFAULT '',
                daily_rate REAL DEFAULT 0,
                hourly_rate REAL DEFAULT 0,
                ot_rate_multiplier REAL DEFAULT 1.5,
                standard_start TEXT DEFAULT '08:00',
                standard_end TEXT DEFAULT '17:00',
                is_active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS attendance(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                work_date TEXT NOT NULL,
                clock_in TEXT,
                clock_out TEXT,
                total_hours REAL DEFAULT 0,
                regular_hours REAL DEFAULT 0,
                ot_hours REAL DEFAULT 0,
                late_minutes INTEGER DEFAULT 0,
                is_corrected INTEGER DEFAULT 0,
                correction_reason TEXT DEFAULT '',
                corrected_by TEXT DEFAULT '',
                corrected_at TEXT DEFAULT '',
                UNIQUE(employee_id, work_date)
            );
            CREATE TABLE IF NOT EXISTS holidays(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                holiday_date TEXT UNIQUE NOT NULL,
                description TEXT DEFAULT '',
                is_paid INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS audit_logs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                admin_username TEXT DEFAULT '',
                action TEXT NOT NULL,
                target_table TEXT DEFAULT '',
                target_id INTEGER,
                details TEXT DEFAULT ''
            );
            """
        )
        if not cur.execute("SELECT 1 FROM admins WHERE username='admin'").fetchone():
            cur.execute(
                "INSERT INTO admins(username,password_hash,full_name) VALUES(?,?,?)",
                ("admin", sha256("admin123"), "ผู้ดูแลระบบ"),
            )
        self.conn.commit()

    def write_audit_log(self, admin_username: str, action: str, target_table: str = "", target_id: Optional[int] = None, details: str = ""):
        self.conn.execute(
            "INSERT INTO audit_logs(timestamp,admin_username,action,target_table,target_id,details) VALUES(?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), admin_username, action, target_table, target_id, details),
        )
        self.conn.commit()

    def authenticate_admin(self, username: str, password: str) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM admins WHERE username=? AND password_hash=?",
            (username, sha256(password)),
        ).fetchone()
        return dict(row) if row else None

    def _emp_from_row(self, row) -> Employee:
        return Employee(
            id=row["id"], employee_code=row["employee_code"], full_name=row["full_name"],
            department=row["department"] or "", position=row["position"] or "",
            daily_rate=float(row["daily_rate"] or 0), hourly_rate=float(row["hourly_rate"] or 0),
            ot_rate_multiplier=float(row["ot_rate_multiplier"] or 1.5),
            standard_start=row["standard_start"] or "08:00", standard_end=row["standard_end"] or "17:00",
            is_active=bool(row["is_active"]),
        )

    def get_all_employees(self) -> List[Employee]:
        rows = self.conn.execute("SELECT * FROM employees ORDER BY employee_code").fetchall()
        return [self._emp_from_row(r) for r in rows]

    def get_employee_by_code(self, code: str) -> Optional[Employee]:
        row = self.conn.execute("SELECT * FROM employees WHERE employee_code=? AND is_active=1", (code,)).fetchone()
        return self._emp_from_row(row) if row else None

    def get_employee(self, emp_id: int) -> Optional[Employee]:
        row = self.conn.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
        return self._emp_from_row(row) if row else None

    def add_employee(self, emp: Employee):
        self.conn.execute(
            """INSERT INTO employees(employee_code,full_name,department,position,daily_rate,hourly_rate,ot_rate_multiplier,standard_start,standard_end,is_active)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (emp.employee_code, emp.full_name, emp.department, emp.position, emp.daily_rate, emp.hourly_rate,
             emp.ot_rate_multiplier, emp.standard_start, emp.standard_end, int(emp.is_active)),
        )
        self.conn.commit()

    def update_employee(self, emp: Employee):
        self.conn.execute(
            """UPDATE employees SET employee_code=?,full_name=?,department=?,position=?,daily_rate=?,hourly_rate=?,ot_rate_multiplier=?,standard_start=?,standard_end=?,is_active=? WHERE id=?""",
            (emp.employee_code, emp.full_name, emp.department, emp.position, emp.daily_rate, emp.hourly_rate,
             emp.ot_rate_multiplier, emp.standard_start, emp.standard_end, int(emp.is_active), emp.id),
        )
        self.conn.commit()

    def delete_employee(self, emp_id: int):
        self.conn.execute("UPDATE employees SET is_active=0 WHERE id=?", (emp_id,))
        self.conn.commit()

    def _recalc_record(self, attendance_id: int):
        row = self.conn.execute("SELECT * FROM attendance WHERE id=?", (attendance_id,)).fetchone()
        if not row:
            return
        emp = self.get_employee(row["employee_id"])
        ci, co = parse_dt(row["clock_in"]), parse_dt(row["clock_out"])
        total = regular = ot = 0.0
        late = 0
        if ci and co and co > ci:
            total = round((co - ci).total_seconds() / 3600, 2)
            regular = min(total, 8.0)
            ot = max(0.0, round(total - 8.0, 2))
            if emp:
                std = datetime.strptime(row["work_date"] + " " + emp.standard_start, "%Y-%m-%d %H:%M")
                late = max(0, int((ci - std).total_seconds() // 60))
        self.conn.execute(
            "UPDATE attendance SET total_hours=?, regular_hours=?, ot_hours=?, late_minutes=? WHERE id=?",
            (total, regular, ot, late, attendance_id),
        )
        self.conn.commit()

    def clock_in(self, employee_id: int, now: datetime) -> Tuple[bool, str]:
        wd = now.strftime("%Y-%m-%d")
        existing = self.conn.execute("SELECT * FROM attendance WHERE employee_id=? AND work_date=?", (employee_id, wd)).fetchone()
        if existing and existing["clock_in"] and not existing["clock_out"]:
            return False, "วันนี้เข้างานแล้ว"
        if existing and existing["clock_in"] and existing["clock_out"]:
            self.conn.execute("UPDATE attendance SET clock_in=?, clock_out=NULL, total_hours=0, regular_hours=0, ot_hours=0 WHERE id=?", (now.isoformat(timespec="seconds"), existing["id"]))
            self.conn.commit()
            return True, "เริ่มรอบงานใหม่"
        self.conn.execute("INSERT OR IGNORE INTO attendance(employee_id,work_date,clock_in) VALUES(?,?,?)", (employee_id, wd, now.isoformat(timespec="seconds")))
        self.conn.commit()
        return True, "บันทึกเวลาเข้างานแล้ว"

    def clock_out(self, employee_id: int, now: datetime) -> Tuple[bool, str]:
        wd = now.strftime("%Y-%m-%d")
        row = self.conn.execute("SELECT * FROM attendance WHERE employee_id=? AND work_date=?", (employee_id, wd)).fetchone()
        if not row or not row["clock_in"]:
            return False, "ยังไม่ได้บันทึกเวลาเข้างาน"
        if row["clock_out"]:
            return False, "วันนี้ออกงานแล้ว"
        self.conn.execute("UPDATE attendance SET clock_out=? WHERE id=?", (now.isoformat(timespec="seconds"), row["id"]))
        self.conn.commit()
        self._recalc_record(row["id"])
        return True, "บันทึกเวลาออกงานแล้ว"

    def get_employee_today_status(self, employee_id: int, date_str: str) -> Optional[Dict]:
        row = self.conn.execute("SELECT * FROM attendance WHERE employee_id=? AND work_date=?", (employee_id, date_str)).fetchone()
        return dict(row) if row else None

    def get_attendance_for_date(self, date_str: str) -> List[Dict]:
        rows = self.conn.execute(
            """SELECT a.*, e.employee_code, e.full_name, e.department FROM attendance a
               JOIN employees e ON e.id=a.employee_id WHERE a.work_date=? ORDER BY e.employee_code""", (date_str,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_attendance_range(self, start: str, end: str) -> List[Dict]:
        rows = self.conn.execute(
            """SELECT a.*, e.employee_code, e.full_name, e.department, e.position FROM attendance a
               JOIN employees e ON e.id=a.employee_id WHERE a.work_date BETWEEN ? AND ? ORDER BY a.work_date,e.employee_code""",
            (start, end),
        ).fetchall()
        return [dict(r) for r in rows]

    def correct_attendance(self, attendance_id: int, clock_in: Optional[str], clock_out: Optional[str], admin_username: str, reason: str) -> bool:
        self.conn.execute(
            "UPDATE attendance SET clock_in=?,clock_out=?,is_corrected=1,correction_reason=?,corrected_by=?,corrected_at=? WHERE id=?",
            (clock_in, clock_out, reason, admin_username, datetime.now().isoformat(timespec="seconds"), attendance_id),
        )
        self.conn.commit()
        self._recalc_record(attendance_id)
        self.write_audit_log(admin_username, "CORRECT_ATTENDANCE", "attendance", attendance_id, reason)
        return True

    def add_holiday(self, h: Holiday) -> bool:
        try:
            self.conn.execute("INSERT INTO holidays(holiday_date,description,is_paid) VALUES(?,?,?)", (h.holiday_date, h.description, int(h.is_paid)))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_holidays(self, year: int) -> List[Holiday]:
        rows = self.conn.execute("SELECT * FROM holidays WHERE holiday_date LIKE ? ORDER BY holiday_date", (f"{year}-%",)).fetchall()
        return [Holiday(id=r["id"], holiday_date=r["holiday_date"], description=r["description"], is_paid=bool(r["is_paid"])) for r in rows]

    def delete_holiday(self, hid: int):
        self.conn.execute("DELETE FROM holidays WHERE id=?", (hid,))
        self.conn.commit()

    def get_audit_logs(self) -> List[Dict]:
        rows = self.conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 200").fetchall()
        return [dict(r) for r in rows]


class PayrollCalculator:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def calculate_all(self, start: str, end: str) -> List[Dict]:
        records = self.db.get_all_attendance_range(start, end)
        by_emp: Dict[int, List[Dict]] = {}
        for r in records:
            by_emp.setdefault(r["employee_id"], []).append(r)
        results = []
        for emp_id, rows in by_emp.items():
            emp = self.db.get_employee(emp_id)
            if not emp:
                continue
            total_days = len({r["work_date"] for r in rows if r.get("clock_in")})
            regular_hours = round(sum(float(r.get("regular_hours") or 0) for r in rows), 2)
            ot_hours = round(sum(float(r.get("ot_hours") or 0) for r in rows), 2)
            late_minutes = int(sum(int(r.get("late_minutes") or 0) for r in rows))
            base_pay = emp.daily_rate * total_days if emp.daily_rate > 0 else emp.hourly_rate * regular_hours
            ot_pay = emp.hourly_rate * emp.ot_rate_multiplier * ot_hours
            late_deduction = emp.hourly_rate * (late_minutes / 60.0)
            gross = base_pay + ot_pay
            net = max(0.0, gross - late_deduction)
            results.append(dict(
                employee_code=emp.employee_code, full_name=emp.full_name, department=emp.department,
                total_days=total_days, regular_hours=regular_hours, ot_hours=ot_hours,
                late_minutes=late_minutes, late_deduction=round(late_deduction, 2),
                gross_pay=round(gross, 2), net_pay=round(net, 2),
            ))
        return results


class ExportEngine:
    def __init__(self):
        self.export_dir = app_dir() / "exports"
        self.export_dir.mkdir(exist_ok=True)

    def export_csv(self, rows: List[Dict], name: str) -> str:
        path = self.export_dir / name
        if not rows:
            return str(path)
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return str(path)


# -------------------------- UI helpers --------------------------
class ThaiButton(Button):
    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(48))
        kwargs.setdefault("font_size", "18sp")
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("color", WHITE)
        super().__init__(**kwargs)


def label(text: str, size="18sp", color=WHITE, **kw) -> Label:
    return Label(text=text, font_size=size, color=color, markup=True, halign="left", valign="middle", **kw)


def toast(title: str, msg: str):
    box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
    box.add_widget(label(msg, color=WHITE))
    btn = ThaiButton(text="ตกลง", background_color=PRIMARY)
    box.add_widget(btn)
    pop = Popup(title=title, content=box, size_hint=(0.88, None), height=dp(230))
    btn.bind(on_release=pop.dismiss)
    pop.open()


def text_input(hint="", multiline=False) -> TextInput:
    return TextInput(hint_text=hint, multiline=multiline, size_hint_y=None, height=dp(46), font_size="18sp", foreground_color=(0,0,0,1))


class BaseScreen(Screen):
    app_ref: "AttendanceApp"
    def root_box(self, title: str) -> BoxLayout:
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        box.add_widget(label(f"[b]{title}[/b]", "24sp", WHITE, size_hint_y=None, height=dp(42)))
        return box

    @property
    def db(self) -> DatabaseManager:
        return self.manager.app_ref.db  # type: ignore

    def go(self, screen: str):
        self.manager.current = screen


class ClockScreen(BaseScreen):
    time_text = StringProperty("")
    status_text = StringProperty("")
    def on_enter(self):
        self.build()
        self._ev = Clock.schedule_interval(self.tick, 1)
        self.tick(0)
    def on_leave(self):
        if hasattr(self, "_ev"):
            self._ev.cancel()
    def build(self):
        self.clear_widgets()
        box = self.root_box("ระบบบันทึกเวลาเข้า-ออกงาน")
        top = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        admin = ThaiButton(text="ผู้ดูแล", background_color=WARNING, size_hint_x=.32)
        admin.bind(on_release=lambda *_: self.go("login"))
        top.add_widget(label("กรอกรหัสพนักงาน แล้วกดเข้า/ออกงาน", color=MUTED))
        top.add_widget(admin)
        box.add_widget(top)
        self.lbl_time = label("", "42sp", PRIMARY, size_hint_y=None, height=dp(72), halign="center")
        box.add_widget(self.lbl_time)
        self.emp_code = text_input("รหัสพนักงาน")
        box.add_widget(self.emp_code)
        row = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(8))
        b1 = ThaiButton(text="เข้างาน", background_color=SUCCESS)
        b2 = ThaiButton(text="ออกงาน", background_color=DANGER)
        ba = ThaiButton(text="อัตโนมัติ", background_color=PRIMARY)
        b1.bind(on_release=lambda *_: self.clock_in())
        b2.bind(on_release=lambda *_: self.clock_out())
        ba.bind(on_release=lambda *_: self.auto_action())
        row.add_widget(b1); row.add_widget(b2); row.add_widget(ba)
        box.add_widget(row)
        self.status = label("", "18sp", MUTED, size_hint_y=None, height=dp(75))
        box.add_widget(self.status)
        box.add_widget(label("ผู้ดูแลเริ่มต้น: admin / admin123", "14sp", MUTED, size_hint_y=None, height=dp(32)))
        self.add_widget(box)
    def tick(self, *_):
        now = datetime.now()
        self.lbl_time.text = now.strftime("%H:%M:%S\n%d/%m/%Y")
    def get_emp(self) -> Optional[Employee]:
        code = self.emp_code.text.strip()
        if not code:
            self.status.text = "กรุณากรอกรหัสพนักงาน"
            return None
        emp = self.db.get_employee_by_code(code)
        if not emp:
            self.status.text = f"ไม่พบรหัสพนักงาน: {code}"
            return None
        return emp
    def clock_in(self):
        emp = self.get_emp()
        if emp:
            ok, msg = self.db.clock_in(emp.id, datetime.now())
            self.status.text = f"{emp.full_name}: {msg}"
            if ok: self.emp_code.text = ""
    def clock_out(self):
        emp = self.get_emp()
        if emp:
            ok, msg = self.db.clock_out(emp.id, datetime.now())
            self.status.text = f"{emp.full_name}: {msg}"
            if ok: self.emp_code.text = ""
    def auto_action(self):
        emp = self.get_emp()
        if not emp: return
        s = self.db.get_employee_today_status(emp.id, today_str())
        if not s or (s.get("clock_in") and s.get("clock_out")):
            self.clock_in()
        else:
            self.clock_out()


class LoginScreen(BaseScreen):
    def on_enter(self):
        self.clear_widgets(); box = self.root_box("เข้าสู่ระบบผู้ดูแล")
        self.user = text_input("ชื่อผู้ใช้")
        self.pw = text_input("รหัสผ่าน"); self.pw.password = True
        box.add_widget(self.user); box.add_widget(self.pw)
        btn = ThaiButton(text="เข้าสู่ระบบ", background_color=PRIMARY)
        back = ThaiButton(text="ย้อนกลับ", background_color=(.35,.35,.35,1))
        btn.bind(on_release=lambda *_: self.login())
        back.bind(on_release=lambda *_: self.go("clock"))
        box.add_widget(btn); box.add_widget(back)
        self.add_widget(box)
    def login(self):
        admin = self.db.authenticate_admin(self.user.text.strip(), self.pw.text)
        if admin:
            self.manager.app_ref.current_admin = admin  # type: ignore
            self.db.write_audit_log(admin["username"], "LOGIN")
            self.go("dashboard")
        else:
            toast("ผิดพลาด", "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")


class DashboardScreen(BaseScreen):
    def on_enter(self):
        self.clear_widgets(); box = self.root_box("เมนูผู้ดูแล")
        items = [
            ("ภาพรวมวันนี้", "today"), ("จัดการพนักงาน", "employees"), ("แก้ไขเวลา", "correction"),
            ("ปฏิทิน / วันหยุด", "holidays"), ("คำนวณเงินเดือน", "payroll"), ("Export รายงาน", "export"),
            ("บันทึกการใช้งาน", "logs"),
        ]
        for txt, scr in items:
            b = ThaiButton(text=txt, background_color=PRIMARY)
            b.bind(on_release=lambda _, s=scr: self.go(s))
            box.add_widget(b)
        out = ThaiButton(text="ออกจากระบบ", background_color=DANGER)
        out.bind(on_release=lambda *_: self.logout())
        box.add_widget(out); self.add_widget(box)
    def logout(self):
        admin = self.manager.app_ref.current_admin  # type: ignore
        if admin: self.db.write_audit_log(admin["username"], "LOGOUT")
        self.go("clock")


class TableScreen(BaseScreen):
    title = ""
    def table(self, rows: List[str]) -> ScrollView:
        grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        for r in rows:
            grid.add_widget(label(r, "16sp", WHITE, size_hint_y=None, height=dp(48)))
        sv = ScrollView(); sv.add_widget(grid); return sv


class TodayScreen(TableScreen):
    def on_enter(self):
        self.clear_widgets(); box = self.root_box("ภาพรวมการเข้างานวันนี้")
        rows = [f"{r['employee_code']} | {r['full_name']} | เข้า {fmt_time(r['clock_in'])} | ออก {fmt_time(r['clock_out'])} | ชม. {r['total_hours']:.2f} | OT {r['ot_hours']:.2f}" for r in self.db.get_attendance_for_date(today_str())]
        box.add_widget(self.table(rows or ["ไม่มีข้อมูลการเข้างานวันนี้"]))
        back = ThaiButton(text="กลับเมนู", background_color=(.35,.35,.35,1)); back.bind(on_release=lambda *_: self.go("dashboard")); box.add_widget(back)
        self.add_widget(box)


class EmployeesScreen(TableScreen):
    def on_enter(self):
        self.clear_widgets(); box = self.root_box("จัดการพนักงาน")
        form = GridLayout(cols=2, size_hint_y=None, height=dp(300), spacing=dp(5))
        self.code = text_input("รหัส*"); self.name = text_input("ชื่อ*"); self.dept = text_input("แผนก"); self.pos = text_input("ตำแหน่ง")
        self.daily = text_input("ค่าแรงรายวัน"); self.hourly = text_input("ค่าแรง/ชม."); self.ot = text_input("OT x เช่น 1.5"); self.start = text_input("เวลาเข้า 08:00"); self.end = text_input("เวลาออก 17:00")
        for w in [self.code,self.name,self.dept,self.pos,self.daily,self.hourly,self.ot,self.start,self.end]: form.add_widget(w)
        box.add_widget(form)
        add = ThaiButton(text="เพิ่มพนักงาน", background_color=SUCCESS); add.bind(on_release=lambda *_: self.add_emp()); box.add_widget(add)
        rows = [f"{e.id}. {e.employee_code} | {e.full_name} | {e.department} | {e.position} | {e.hourly_rate:.2f}/ชม. | {'ใช้งาน' if e.is_active else 'ปิด'}" for e in self.db.get_all_employees()]
        box.add_widget(self.table(rows or ["ยังไม่มีข้อมูลพนักงาน"]))
        back = ThaiButton(text="กลับเมนู", background_color=(.35,.35,.35,1)); back.bind(on_release=lambda *_: self.go("dashboard")); box.add_widget(back)
        self.add_widget(box)
    def add_emp(self):
        if not self.code.text.strip() or not self.name.text.strip():
            toast("ผิดพลาด", "กรอกรหัสและชื่อพนักงาน"); return
        try:
            emp = Employee(employee_code=self.code.text.strip(), full_name=self.name.text.strip(), department=self.dept.text.strip(), position=self.pos.text.strip(), daily_rate=float(self.daily.text or 0), hourly_rate=float(self.hourly.text or 0), ot_rate_multiplier=float(self.ot.text or 1.5), standard_start=self.start.text.strip() or "08:00", standard_end=self.end.text.strip() or "17:00")
            self.db.add_employee(emp); self.db.write_audit_log("admin", "ADD_EMPLOYEE", "employees", details=emp.full_name)
            toast("สำเร็จ", "เพิ่มพนักงานแล้ว"); self.on_enter()
        except Exception as e: toast("บันทึกไม่สำเร็จ", str(e))


class CorrectionScreen(TableScreen):
    def on_enter(self):
        self.clear_widgets(); box = self.root_box("แก้ไขเวลาเข้า-ออกงาน")
        self.date = text_input("วันที่ YYYY-MM-DD"); self.date.text = today_str(); self.att_id = text_input("ID รายการ"); self.ci = text_input("เวลาเข้า YYYY-MM-DD HH:MM:SS"); self.co = text_input("เวลาออก YYYY-MM-DD HH:MM:SS"); self.reason = text_input("เหตุผล")
        for w in [self.date,self.att_id,self.ci,self.co,self.reason]: box.add_widget(w)
        row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
        load = ThaiButton(text="โหลดรายการ", background_color=PRIMARY); save = ThaiButton(text="บันทึกแก้ไข", background_color=WARNING)
        load.bind(on_release=lambda *_: self.load_records(box)); save.bind(on_release=lambda *_: self.save())
        row.add_widget(load); row.add_widget(save); box.add_widget(row)
        self.result_area = BoxLayout(); box.add_widget(self.result_area)
        back = ThaiButton(text="กลับเมนู", background_color=(.35,.35,.35,1)); back.bind(on_release=lambda *_: self.go("dashboard")); box.add_widget(back)
        self.add_widget(box); self.load_records(box)
    def load_records(self, *_):
        if self.result_area.children: self.result_area.clear_widgets()
        rows = [f"ID {r['id']} | {r['employee_code']} {r['full_name']} | เข้า {fmt_time(r['clock_in'])} | ออก {fmt_time(r['clock_out'])}" for r in self.db.get_attendance_for_date(self.date.text.strip())]
        self.result_area.add_widget(self.table(rows or ["ไม่พบข้อมูลวันที่นี้"]))
    def save(self):
        try:
            aid = int(self.att_id.text.strip())
            if not self.reason.text.strip(): raise ValueError("กรุณาระบุเหตุผล")
            admin = self.manager.app_ref.current_admin or {"username":"admin"}  # type: ignore
            self.db.correct_attendance(aid, self.ci.text.strip() or None, self.co.text.strip() or None, admin["username"], self.reason.text.strip())
            toast("สำเร็จ", "แก้ไขเวลาแล้ว"); self.on_enter()
        except Exception as e: toast("ผิดพลาด", str(e))


class HolidaysScreen(TableScreen):
    def on_enter(self):
        self.clear_widgets(); box = self.root_box("ปฏิทิน / วันหยุด")
        self.hdate = text_input("วันที่ YYYY-MM-DD"); self.hdesc = text_input("รายละเอียด")
        box.add_widget(self.hdate); box.add_widget(self.hdesc)
        add = ThaiButton(text="เพิ่มวันหยุด", background_color=SUCCESS); add.bind(on_release=lambda *_: self.add_holiday()); box.add_widget(add)
        rows = [f"{h.id}. {h.holiday_date} | {h.description} | {'มีค่าจ้าง' if h.is_paid else 'ไม่มีค่าจ้าง'}" for h in self.db.get_holidays(datetime.now().year)]
        box.add_widget(self.table(rows or ["ไม่มีวันหยุดที่บันทึกไว้"]))
        back = ThaiButton(text="กลับเมนู", background_color=(.35,.35,.35,1)); back.bind(on_release=lambda *_: self.go("dashboard")); box.add_widget(back)
        self.add_widget(box)
    def add_holiday(self):
        ok = self.db.add_holiday(Holiday(holiday_date=self.hdate.text.strip(), description=self.hdesc.text.strip(), is_paid=True))
        toast("ผลลัพธ์", "บันทึกแล้ว" if ok else "วันที่ซ้ำหรือข้อมูลผิดพลาด"); self.on_enter()


class PayrollScreen(TableScreen):
    def on_enter(self):
        self.clear_widgets(); box = self.root_box("คำนวณเงินเดือน")
        self.start = text_input("ตั้งแต่ YYYY-MM-DD"); self.start.text = datetime.now().strftime("%Y-%m-01")
        self.end = text_input("ถึง YYYY-MM-DD"); self.end.text = today_str()
        box.add_widget(self.start); box.add_widget(self.end)
        run = ThaiButton(text="คำนวณ", background_color=PRIMARY); run.bind(on_release=lambda *_: self.run(box)); box.add_widget(run)
        self.result_area = BoxLayout(); box.add_widget(self.result_area)
        back = ThaiButton(text="กลับเมนู", background_color=(.35,.35,.35,1)); back.bind(on_release=lambda *_: self.go("dashboard")); box.add_widget(back)
        self.add_widget(box)
    def run(self, *_):
        self.result_area.clear_widgets()
        res = PayrollCalculator(self.db).calculate_all(self.start.text.strip(), self.end.text.strip())
        self.manager.app_ref.payroll_results = res  # type: ignore
        rows = [f"{r['employee_code']} | {r['full_name']} | วัน {r['total_days']} | ปกติ {r['regular_hours']} | OT {r['ot_hours']} | หักสาย {r['late_deduction']:.2f} | สุทธิ {r['net_pay']:.2f}" for r in res]
        self.result_area.add_widget(self.table(rows or ["ไม่พบข้อมูลในช่วงวันที่นี้"]))


class ExportScreen(BaseScreen):
    def on_enter(self):
        self.clear_widgets(); box = self.root_box("Export รายงาน")
        self.start = text_input("ตั้งแต่ YYYY-MM-DD"); self.start.text = datetime.now().strftime("%Y-%m-01")
        self.end = text_input("ถึง YYYY-MM-DD"); self.end.text = today_str()
        box.add_widget(self.start); box.add_widget(self.end)
        a = ThaiButton(text="Export Attendance CSV", background_color=SUCCESS); p = ThaiButton(text="Export Payroll CSV", background_color=PRIMARY)
        a.bind(on_release=lambda *_: self.exp_att()); p.bind(on_release=lambda *_: self.exp_pay())
        box.add_widget(a); box.add_widget(p)
        back = ThaiButton(text="กลับเมนู", background_color=(.35,.35,.35,1)); back.bind(on_release=lambda *_: self.go("dashboard")); box.add_widget(back)
        self.add_widget(box)
    def exp_att(self):
        rows = self.db.get_all_attendance_range(self.start.text.strip(), self.end.text.strip())
        path = ExportEngine().export_csv(rows, f"attendance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        toast("Export สำเร็จ", f"บันทึกไฟล์ที่:\n{path}")
    def exp_pay(self):
        rows = PayrollCalculator(self.db).calculate_all(self.start.text.strip(), self.end.text.strip())
        path = ExportEngine().export_csv(rows, f"payroll_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        toast("Export สำเร็จ", f"บันทึกไฟล์ที่:\n{path}")


class LogsScreen(TableScreen):
    def on_enter(self):
        self.clear_widgets(); box = self.root_box("บันทึกการใช้งาน")
        rows = [f"{l['timestamp']} | {l['admin_username']} | {l['action']} | {l['details']}" for l in self.db.get_audit_logs()]
        box.add_widget(self.table(rows or ["ยังไม่มีบันทึก"]))
        back = ThaiButton(text="กลับเมนู", background_color=(.35,.35,.35,1)); back.bind(on_release=lambda *_: self.go("dashboard")); box.add_widget(back)
        self.add_widget(box)


class AttendanceApp(App):
    def build(self):
        self.title = "ระบบบันทึกเวลาและคำนวณเงินเดือน"
        self.db = DatabaseManager()
        self.current_admin = None
        self.payroll_results = []
        sm = ScreenManager()
        sm.app_ref = self  # type: ignore
        for cls, name in [(ClockScreen,"clock"),(LoginScreen,"login"),(DashboardScreen,"dashboard"),(TodayScreen,"today"),(EmployeesScreen,"employees"),(CorrectionScreen,"correction"),(HolidaysScreen,"holidays"),(PayrollScreen,"payroll"),(ExportScreen,"export"),(LogsScreen,"logs")]:
            sm.add_widget(cls(name=name))
        sm.current = "clock"
        return sm


if __name__ == "__main__":
    AttendanceApp().run()
