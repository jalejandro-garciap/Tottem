from __future__ import annotations
from typing import List, Dict, Any
from services.sales import connect

def _ensure_schema() -> None:
    conn = connect()
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS employee (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                emp_no TEXT NOT NULL,
                full_name TEXT NOT NULL,
                phone TEXT,
                active INTEGER NOT NULL DEFAULT 1
            );
            """
        )

def list_employees() -> List[Dict[str, Any]]:
    _ensure_schema()
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, emp_no, full_name, phone, active "
        "FROM employee ORDER BY emp_no;"
    )
    rows = cur.fetchall()
    return [dict(r) for r in rows]

def get_employee(employee_id: int) -> Dict[str, Any] | None:
    _ensure_schema()
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, emp_no, full_name, phone, active "
        "FROM employee WHERE id = ?;",
        (employee_id,),
    )
    r = cur.fetchone()
    return dict(r) if r else None

def create_employee(emp_no: str, full_name: str, phone: str, active: bool) -> int:
    _ensure_schema()
    conn = connect()
    with conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO employee(emp_no, full_name, phone, active) "
            "VALUES(?,?,?,?);",
            (emp_no, full_name, phone, 1 if active else 0),
        )
        return cur.lastrowid

def update_employee(
    employee_id: int,
    emp_no: str,
    full_name: str,
    phone: str,
    active: bool,
) -> None:
    _ensure_schema()
    conn = connect()
    with conn:
        conn.execute(
            "UPDATE employee "
            "SET emp_no=?, full_name=?, phone=?, active=? "
            "WHERE id=?;",
            (emp_no, full_name, phone, 1 if active else 0, employee_id),
        )

def set_employee_active(employee_id: int, active: bool) -> None:
    _ensure_schema()
    conn = connect()
    with conn:
        conn.execute(
            "UPDATE employee SET active=? WHERE id=?;",
            (1 if active else 0, employee_id),
        )

def delete_employee(employee_id: int) -> None:
    _ensure_schema()
    conn = connect()
    with conn:
        conn.execute("DELETE FROM employee WHERE id=?;", (employee_id,))

