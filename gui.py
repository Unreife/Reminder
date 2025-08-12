import os
import shutil
import sqlite3
import smtplib
import ssl
import email.policy
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from typing import List, Optional

import tkinter as tk
from tkinter import ttk, messagebox

import customtkinter as ctk


# Data and DB paths
DATA_DIR = os.path.join("data")
DB_PATH = os.path.join(DATA_DIR, "orders.db")

# Expected schema (fresh start)
EXPECTED_COLUMNS = [
    "id",
    "customer_name",
    "address",
    "purchase_date",
    "planned_delivery_date",
    "model",
    "notes",
    "notified_two_days",
    "created_at",
]

# SMTP configuration (as requested)
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "your email"
SMTP_PASS = "your app password without spaces"  # spaces removed
SMTP_RECIPIENTS = [
    "recipient email adresses"
]


def ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def connect_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def get_table_columns(con: sqlite3.Connection, table: str) -> List[str]:
    try:
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
        return [r[1] for r in rows]
    except Exception:
        return []


def backup_database() -> Optional[str]:
    if not os.path.exists(DB_PATH):
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(DATA_DIR, f"orders_backup_{ts}.db")
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


def create_fresh_schema(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            address TEXT,
            purchase_date TEXT NOT NULL,
            planned_delivery_date TEXT NOT NULL,
            model TEXT NOT NULL,
            notes TEXT,
            notified_two_days INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    con.commit()


def ensure_fresh_database() -> None:
    ensure_data_dir()
    con = connect_db()
    try:
        cols = get_table_columns(con, "orders")
        if not cols:
            create_fresh_schema(con)
            return
        if sorted(cols) != sorted(EXPECTED_COLUMNS):
            backup_database()
            con.execute("DROP TABLE IF EXISTS orders")
            con.commit()
            create_fresh_schema(con)
    finally:
        con.close()


class OrderReminderApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("OrderReminder")
        self.geometry("1000x640")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        ensure_fresh_database()

        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self._load_orders()
        # Auto-send notifications shortly after startup
        self.after(1500, lambda: self._send_notifications(silent=True))

    def _build_ui(self) -> None:
        top = ctk.CTkFrame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        ctk.CTkButton(top, text="Add Order", command=self._open_add_dialog).pack(side=tk.LEFT, padx=(0, 10))
        ctk.CTkButton(top, text="Send Notifications", command=self._send_notifications).pack(side=tk.LEFT, padx=(0, 10))
        ctk.CTkButton(top, text="Delete Selected", command=self._delete_selected).pack(side=tk.LEFT, padx=(0, 10))
        ctk.CTkButton(top, text="Refresh", command=self._load_orders).pack(side=tk.LEFT)

        # Table
        table = ctk.CTkFrame(self)
        table.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.columns = (
            "id",
            "customer_name",
            "address",
            "purchase_date",
            "planned_delivery_date",
            "model",
            "notes",
            "notified_two_days",
            "created_at",
        )
        self.tree = ttk.Treeview(table, columns=self.columns, show="headings")
        for col in self.columns:
            self.tree.heading(col, text=col)
            width = 150
            if col in ("id", "notified_two_days"):
                width = 90
            if col == "notes":
                width = 240
            self.tree.column(col, width=width, anchor=tk.W)

        vsb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)

        ctk.CTkLabel(self, textvariable=self.status_var, anchor="w").pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 10))

    def _load_orders(self) -> None:
        try:
            for iid in self.tree.get_children():
                self.tree.delete(iid)
            con = connect_db()
            rows = con.execute(
                """
                SELECT id, customer_name, address, purchase_date, planned_delivery_date, model, notes, notified_two_days, created_at
                FROM orders
                ORDER BY date(planned_delivery_date) ASC, id ASC
                """
            ).fetchall()
            for r in rows:
                self.tree.insert(
                    "",
                    tk.END,
                    values=(
                        r["id"],
                        r["customer_name"],
                        r["address"],
                        r["purchase_date"],
                        r["planned_delivery_date"],
                        r["model"],
                        r["notes"],
                        r["notified_two_days"],
                        r["created_at"],
                    ),
                )
        except Exception as exc:
            messagebox.showerror("Load Orders", str(exc))
        finally:
            try:
                con.close()
            except Exception:
                pass

    def _open_add_dialog(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Order")
        dialog.geometry("420x540")
        dialog.grab_set()

        frame = ctk.CTkFrame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        ctk.CTkLabel(frame, text="Customer Name").grid(row=0, column=0, sticky="w")
        customer_entry = ctk.CTkEntry(frame)
        customer_entry.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(frame, text="Address (optional)").grid(row=2, column=0, sticky="w")
        address_entry = ctk.CTkEntry(frame)
        address_entry.grid(row=3, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(frame, text="Purchase Date (YYYY-MM-DD)").grid(row=4, column=0, sticky="w")
        purchase_entry = ctk.CTkEntry(frame)
        purchase_entry.insert(0, date.today().strftime("%Y-%m-%d"))
        purchase_entry.grid(row=5, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(frame, text="Planned Delivery Date (YYYY-MM-DD)").grid(row=6, column=0, sticky="w")
        planned_entry = ctk.CTkEntry(frame)
        planned_entry.insert(0, (date.today() + timedelta(days=7)).strftime("%Y-%m-%d"))
        planned_entry.grid(row=7, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(frame, text="Model").grid(row=8, column=0, sticky="w")
        model_entry = ctk.CTkEntry(frame)
        model_entry.grid(row=9, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(frame, text="Notes (optional)").grid(row=10, column=0, sticky="w")
        notes_entry = ctk.CTkEntry(frame)
        notes_entry.grid(row=11, column=0, sticky="ew", pady=(0, 8))

        frame.columnconfigure(0, weight=1)

        def on_save() -> None:
            customer = customer_entry.get().strip()
            address = address_entry.get().strip()
            purchase_txt = purchase_entry.get().strip()
            planned_txt = planned_entry.get().strip()
            model_txt = model_entry.get().strip()
            notes_txt = notes_entry.get().strip()

            if not customer or not purchase_txt or not planned_txt or not model_txt:
                messagebox.showwarning("Add Order", "Customer, Purchase Date, Planned Delivery Date, and Model are required.")
                return
            try:
                datetime.strptime(purchase_txt, "%Y-%m-%d")
                datetime.strptime(planned_txt, "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Add Order", "Invalid date format. Use YYYY-MM-DD.")
                return
            try:
                con = connect_db()
                con.execute(
                    """
                    INSERT INTO orders (
                        customer_name, address, purchase_date, planned_delivery_date, model, notes
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (customer, address or None, purchase_txt, planned_txt, model_txt, notes_txt or None),
                )
                con.commit()
                dialog.destroy()
                self.status_var.set("Order added")
                self._load_orders()
            except Exception as exc:
                messagebox.showerror("Add Order", str(exc))
            finally:
                try:
                    con.close()
                except Exception:
                    pass

        buttons = ctk.CTkFrame(dialog)
        buttons.pack(fill=tk.X, padx=16, pady=(0, 16))
        ctk.CTkButton(buttons, text="Save", command=on_save).pack(side=tk.RIGHT, padx=(8, 0))
        ctk.CTkButton(buttons, text="Cancel", fg_color="gray", command=dialog.destroy).pack(side=tk.RIGHT)

    def _delete_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Delete", "Select at least one order to delete.")
            return
        if not messagebox.askyesno("Delete", f"Delete {len(selection)} selected order(s)?"):
            return
        try:
            ids: List[int] = []
            for item in selection:
                values = self.tree.item(item, "values")
                ids.append(int(values[0]))
            con = connect_db()
            con.executemany("DELETE FROM orders WHERE id = ?", [(i,) for i in ids])
            con.commit()
            self.status_var.set("Deleted selected orders")
            self._load_orders()
        except Exception as exc:
            messagebox.showerror("Delete", str(exc))
        finally:
            try:
                con.close()
            except Exception:
                pass

    def _send_notifications(self, silent: bool = False) -> None:
        try:
            target_date = (date.today() + timedelta(days=2)).strftime("%Y-%m-%d")
            con = connect_db()
            rows = con.execute(
                """
                SELECT id, customer_name, model, planned_delivery_date
                FROM orders
                WHERE planned_delivery_date = ? AND IFNULL(notified_two_days, 0) = 0
                ORDER BY id
                """,
                (target_date,),
            ).fetchall()
            if not rows:
                if not silent:
                    messagebox.showinfo("Notifications", "No orders due in 2 days (or already notified).")
                return

            subject = f"OrderReminder: {len(rows)} order(s) due in 2 days ({target_date})"
            lines = ["You have the following order(s) due in 2 days:", ""]
            for r in rows:
                lines.append(f"- #{r['id']}: {r['model']} for {r['customer_name']} (planned delivery {r['planned_delivery_date']})")
            lines.append("")
            lines.append("This is an automated reminder from OrderReminder.")
            body = "\n".join(lines)

            self._send_email(subject, body)

            ids = [(int(r["id"]),) for r in rows]
            con.executemany("UPDATE orders SET notified_two_days = 1 WHERE id = ?", ids)
            con.commit()
            if not silent:
                messagebox.showinfo("Notifications", "Notification email sent and orders marked as notified.")
            self._load_orders()
        except Exception as exc:
            if not silent:
                messagebox.showerror("Notifications", str(exc))
        finally:
            try:
                con.close()
            except Exception:
                pass

    def _send_email(self, subject: str, body: str) -> None:
        # Build UTF-8 safe message
        msg = EmailMessage(policy=email.policy.SMTP)
        msg["From"] = SMTP_USER
        msg["To"] = ", ".join(SMTP_RECIPIENTS)
        msg["Subject"] = subject
        msg.set_content(body, charset="utf-8")

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            # Announce UTF8 capability if supported
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASS)
            try:
                # Request SMTPUTF8 to avoid ascii coercion
                server.send_message(msg, mail_options=["SMTPUTF8"]) 
            except UnicodeEncodeError:
                # Fallback: send raw bytes
                server.sendmail(SMTP_USER, SMTP_RECIPIENTS, msg.as_bytes())


def main() -> None:
    app = OrderReminderApp()
    app.mainloop()


if __name__ == "__main__":
    main()

