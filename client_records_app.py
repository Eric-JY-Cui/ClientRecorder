import calendar
import sqlite3
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from receipt_generator import generate_receipt

DB_FILE = "client_records.db"
DATE_FORMAT = "%Y-%m-%d"


class DatePicker(tk.Frame):
    """A readonly date field with a popup calendar."""
    def __init__(self, parent, initial=None, command=None):
        super().__init__(parent)
        self.command = command
        self.variable = tk.StringVar(value=initial or date.today().strftime(DATE_FORMAT))

        self.entry = ttk.Entry(self, textvariable=self.variable, state="readonly", width=14)
        self.entry.pack(side="left", fill="x", expand=True)
        ttk.Button(self, text="📅", width=3, command=self.open_calendar).pack(side="left", padx=(3, 0))

    def get(self):
        return self.variable.get()

    def set(self, value):
        self.variable.set(value or date.today().strftime(DATE_FORMAT))

    def open_calendar(self):
        try:
            selected = date.fromisoformat(self.variable.get())
        except ValueError:
            selected = date.today()
        CalendarPopup(self, selected, self.set, self.command)


class CalendarPopup(tk.Toplevel):
    def __init__(self, parent, selected_date, callback, change_callback=None):
        super().__init__(parent)
        self.title("Select Date")
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.grab_set()

        self.callback = callback
        self.change_callback = change_callback
        self.year = selected_date.year
        self.month = selected_date.month

        frame = ttk.Frame(self, padding=8)
        frame.pack(fill="both", expand=True)

        nav = ttk.Frame(frame)
        nav.pack(fill="x", pady=(0, 6))
        ttk.Button(nav, text="◀", width=3, command=self.previous_month).pack(side="left")
        self.title_label = ttk.Label(nav, anchor="center", font=("TkDefaultFont", 10, "bold"))
        self.title_label.pack(side="left", fill="x", expand=True)
        ttk.Button(nav, text="▶", width=3, command=self.next_month).pack(side="right")

        self.days_frame = ttk.Frame(frame)
        self.days_frame.pack()
        self.render()

    def render(self):
        for child in self.days_frame.winfo_children():
            child.destroy()

        self.title_label.config(text=f"{calendar.month_name[self.month]} {self.year}")
        headers = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        for col, name in enumerate(headers):
            ttk.Label(self.days_frame, text=name, width=4, anchor="center").grid(row=0, column=col, pady=2)

        weeks = calendar.monthcalendar(self.year, self.month)
        today = date.today()
        for row, week in enumerate(weeks, start=1):
            for col, day_num in enumerate(week):
                if day_num == 0:
                    ttk.Label(self.days_frame, text="", width=4).grid(row=row, column=col, padx=1, pady=1)
                    continue
                d = date(self.year, self.month, day_num)
                button = ttk.Button(
                    self.days_frame,
                    text=str(day_num),
                    width=4,
                    command=lambda chosen=d: self.select_date(chosen),
                )
                button.grid(row=row, column=col, padx=1, pady=1)

    def select_date(self, selected):
        self.callback(selected.strftime(DATE_FORMAT))
        if self.change_callback:
            self.change_callback()
        self.destroy()

    def previous_month(self):
        self.month -= 1
        if self.month == 0:
            self.month = 12
            self.year -= 1
        self.render()

    def next_month(self):
        self.month += 1
        if self.month == 13:
            self.month = 1
            self.year += 1
        self.render()


class ClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Client Records")
        self.root.geometry("1350x820")
        self.root.minsize(1100, 700)

        self.conn = sqlite3.connect(DB_FILE)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.create_tables()

        self.selected_client_id = None
        self.selected_visit_id = None
        self.selected_balance_transaction_id = None

        self.build_ui()
        self.clear_client_form()
        self.load_clients()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    # ---------------- Database ----------------

    def create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                legal_name TEXT NOT NULL,
                address TEXT,
                phone TEXT,
                email TEXT,
                notes TEXT,
                balance REAL NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                visit_date TEXT NOT NULL,
                reason TEXT,
                treatment_modality TEXT,
                duration INTEGER NOT NULL DEFAULT 0,
                cost_subtotal REAL NOT NULL DEFAULT 0,
                cost_total REAL NOT NULL DEFAULT 0,
                billed INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS balance_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                recorded_billing_date TEXT NOT NULL,
                actual_billing_date TEXT,
                amount REAL NOT NULL,
                note TEXT,
                transaction_type TEXT NOT NULL DEFAULT 'balance',
                visit_id INTEGER,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE,
                FOREIGN KEY (visit_id) REFERENCES visits(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS visit_field_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                field_name TEXT NOT NULL,
                value TEXT NOT NULL,
                UNIQUE(field_name, value)
            );
        """)
        self.conn.commit()

    # ---------------- UI ----------------

    def build_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Client Records", font=("TkDefaultFont", 18, "bold")).pack(anchor="w", pady=(0, 10))

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill="both", expand=True)

        self.clients_tab = ttk.Frame(self.notebook, padding=10)
        self.visits_tab = ttk.Frame(self.notebook, padding=10)
        self.visit_selection_tab = ttk.Frame(self.notebook, padding=10)
        self.balance_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.clients_tab, text="Clients")
        self.notebook.add(self.visits_tab, text="Visits")
        self.notebook.add(self.visit_selection_tab, text="Visit Selection")
        self.notebook.add(self.balance_tab, text="Balance")

        self.build_clients_tab()
        self.build_visits_tab()
        self.build_visit_selection_tab()
        self.build_balance_tab()
        self.load_visit_field_history()

    def build_clients_tab(self):
        form = ttk.LabelFrame(self.clients_tab, text="Basic Client Information", padding=10)
        form.pack(fill="x", pady=(0, 10))

        fields = [
            ("Username:", self.make_entry(form), 0, 0),
            ("Legal Name:", self.make_entry(form), 0, 2),
            ("Address:", self.make_entry(form), 1, 0),
            ("Phone:", self.make_entry(form), 1, 2),
            ("Email:", self.make_entry(form), 2, 0),
        ]
        for label, widget, row, col in fields:
            ttk.Label(form, text=label).grid(row=row, column=col, sticky="w", padx=5, pady=5)
            widget.grid(row=row, column=col + 1, sticky="ew", padx=5, pady=5)

        self.username, self.legal_name, self.address, self.phone, self.email = [x[1] for x in fields]

        ttk.Label(form, text="Note:").grid(row=3, column=0, sticky="nw", padx=5, pady=5)
        self.client_notes = tk.Text(form, height=4)
        self.client_notes.grid(row=3, column=1, columnspan=3, sticky="ew", padx=5, pady=5)

        buttons = ttk.Frame(form)
        buttons.grid(row=4, column=0, columnspan=4, sticky="w", padx=5, pady=5)
        ttk.Button(buttons, text="New / Clear", command=self.clear_client_form).pack(side="left", padx=(0, 5))
        ttk.Button(buttons, text="Save Client", command=self.save_client).pack(side="left", padx=5)
        ttk.Button(buttons, text="Delete Client", command=self.delete_client).pack(side="left", padx=5)
        for col in range(4):
            form.columnconfigure(col, weight=1)

        search_frame = ttk.Frame(self.clients_tab)
        search_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(search_frame, text="Search Clients:").pack(side="left", padx=(0, 8))
        self.client_search_var = tk.StringVar()
        self.client_search = ttk.Entry(search_frame, textvariable=self.client_search_var)
        self.client_search.pack(side="left", fill="x", expand=True)
        self.client_search_var.trace_add("write", lambda *_: self.load_clients())
        ttk.Button(search_frame, text="Clear", command=self.clear_client_search).pack(side="left", padx=(8, 0))

        listing = ttk.LabelFrame(self.clients_tab, text="Client List", padding=10)
        listing.pack(fill="both", expand=True)
        columns = ("username", "legal_name", "balance", "note")
        self.client_tree = ttk.Treeview(listing, columns=columns, show="headings", selectmode="browse")
        for col, heading, width in [
            ("username", "Username", 180), ("legal_name", "Legal Name", 280),
            ("balance", "Balance", 130), ("note", "Note", 420)
        ]:
            self.client_tree.heading(col, text=heading)
            self.client_tree.column(col, width=width)
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.client_tree.yview)
        self.client_tree.configure(yscrollcommand=scroll.set)
        self.client_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.client_tree.bind("<<TreeviewSelect>>", self.on_client_selected)

    def build_visits_tab(self):
        form = ttk.LabelFrame(self.visits_tab, text="Visit Information", padding=10)
        form.pack(fill="x", pady=(0, 10))

        ttk.Label(form, text="Client:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.visit_client_label = ttk.Label(form, text="No client selected", font=("TkDefaultFont", 10, "bold"))
        self.visit_client_label.grid(row=0, column=1, columnspan=3, sticky="w", padx=5, pady=5)

        ttk.Label(form, text="Visit Date:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.visit_date = DatePicker(form)
        self.visit_date.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(form, text="Reason:").grid(row=1, column=2, sticky="w", padx=5, pady=5)
        self.visit_reason = self.make_history_combo(form, "reason")
        self.visit_reason.grid(row=1, column=3, sticky="ew", padx=5, pady=5)

        ttk.Label(form, text="Treatment Modality:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.treatment_modality = self.make_history_combo(form, "treatment_modality")
        self.treatment_modality.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(form, text="Duration:").grid(row=2, column=2, sticky="w", padx=5, pady=5)
        self.visit_duration = self.make_history_combo(form, "duration")
        self.visit_duration.grid(row=2, column=3, sticky="ew", padx=5, pady=5)

        ttk.Label(form, text="Cost Subtotal:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.visit_subtotal = self.make_history_combo(form, "cost_subtotal")
        self.visit_subtotal.grid(row=3, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(form, text="Cost Total:").grid(row=3, column=2, sticky="w", padx=5, pady=5)
        self.visit_total = self.make_history_combo(form, "cost_total")
        self.visit_total.grid(row=3, column=3, sticky="ew", padx=5, pady=5)

        self.visit_billed_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="Billed", variable=self.visit_billed_var).grid(row=4, column=2, sticky="w", padx=5, pady=5)

        ttk.Label(form, text="Note:").grid(row=5, column=0, sticky="nw", padx=5, pady=5)
        self.visit_notes = tk.Text(form, height=5)
        self.visit_notes.grid(row=5, column=1, columnspan=3, sticky="ew", padx=5, pady=5)

        buttons = ttk.Frame(form)
        buttons.grid(row=6, column=0, columnspan=4, sticky="w", padx=5, pady=5)
        ttk.Button(buttons, text="New / Clear", command=self.clear_visit_form).pack(side="left", padx=(0, 5))
        ttk.Button(buttons, text="Save Visit", command=self.save_visit).pack(side="left", padx=5)
        for col in range(4):
            form.columnconfigure(col, weight=1)

        listing = ttk.LabelFrame(self.visits_tab, text="Selected Client's Visit History", padding=10)
        listing.pack(fill="both", expand=True)
        columns = ("date", "reason", "modality", "duration", "subtotal", "total", "billed", "note")
        self.visit_tree = ttk.Treeview(listing, columns=columns, show="headings", selectmode="browse")
        for col, heading, width in [
            ("date", "Visit Date", 110), ("reason", "Reason", 180),
            ("modality", "Treatment Modality", 190), ("duration", "Duration", 90),
            ("subtotal", "Subtotal", 95), ("total", "Total", 95), ("billed", "Billed", 75), ("note", "Note", 350)
        ]:
            self.visit_tree.heading(col, text=heading)
            self.visit_tree.column(col, width=width)
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.visit_tree.yview)
        self.visit_tree.configure(yscrollcommand=scroll.set)
        self.visit_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.visit_tree.bind("<<TreeviewSelect>>", self.on_visit_selected)
        self.visit_tree.bind("<Double-1>", self.on_visit_double_click)


    def build_visit_selection_tab(self):
        """Separate multi-selection module for batch visit actions such as receipts."""
        top = ttk.Frame(self.visit_selection_tab)
        top.pack(fill="x", pady=(0, 10))

        ttk.Label(top, text="Client:").pack(side="left", padx=(0, 8))
        self.selection_client_label = ttk.Label(
            top, text="No client selected", font=("TkDefaultFont", 10, "bold")
        )
        self.selection_client_label.pack(side="left")

        ttk.Label(
            self.visit_selection_tab,
            text="Select multiple visits for batch actions. This selection is separate from visit editing.",
        ).pack(anchor="w", pady=(0, 5))

        listing = ttk.LabelFrame(
            self.visit_selection_tab,
            text="Visits Available for Batch Actions",
            padding=10,
        )
        listing.pack(fill="both", expand=True)

        columns = ("date", "reason", "modality", "duration", "subtotal", "total", "billed", "note")
        self.visit_selection_tree = ttk.Treeview(
            listing, columns=columns, show="headings", selectmode="extended"
        )
        for col, heading, width in [
            ("date", "Visit Date", 110),
            ("reason", "Reason", 180),
            ("modality", "Treatment Modality", 190),
            ("duration", "Duration", 90),
            ("subtotal", "Subtotal", 95),
            ("total", "Total", 95),
            ("billed", "Billed", 75),
            ("note", "Note", 350),
        ]:
            self.visit_selection_tree.heading(col, text=heading)
            self.visit_selection_tree.column(col, width=width)

        scroll = ttk.Scrollbar(
            listing, orient="vertical", command=self.visit_selection_tree.yview
        )
        self.visit_selection_tree.configure(yscrollcommand=scroll.set)
        self.visit_selection_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        buttons = ttk.Frame(self.visit_selection_tab)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(
            buttons, text="Generate Receipt", command=self.open_receipt_dialog
        ).pack(side="right")

    def build_balance_tab(self):
        top = ttk.Frame(self.balance_tab)
        top.pack(fill="x", pady=(0, 10))
        selected = ttk.LabelFrame(top, text="Selected Client", padding=10)
        selected.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.balance_client_label = ttk.Label(selected, text="No client selected", font=("TkDefaultFont", 11, "bold"))
        self.balance_client_label.pack(anchor="w")

        current = ttk.LabelFrame(top, text="Current Balance", padding=10)
        current.pack(side="left", padx=(5, 0))
        self.current_balance_label = ttk.Label(current, text="$0.00", font=("TkDefaultFont", 18, "bold"))
        self.current_balance_label.pack()

        form = ttk.LabelFrame(self.balance_tab, text="Add Balance", padding=10)
        form.pack(fill="x", pady=(0, 10))

        ttk.Label(form, text="Recorded Billing Date:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.balance_recorded_date = DatePicker(form)
        self.balance_recorded_date.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(form, text="Actual Billing Date:").grid(row=0, column=2, sticky="w", padx=5, pady=5)
        self.balance_actual_date = DatePicker(form)
        self.balance_actual_date.grid(row=0, column=3, sticky="w", padx=5, pady=5)

        ttk.Label(form, text="Amount:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.balance_amount = self.make_entry(form)
        self.balance_amount.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        ttk.Label(form, text="Positive increases; negative decreases balance.").grid(row=1, column=2, columnspan=2, sticky="w", padx=5, pady=5)

        ttk.Label(form, text="Note:").grid(row=2, column=0, sticky="nw", padx=5, pady=5)
        self.balance_note = tk.Text(form, height=4)
        self.balance_note.grid(row=2, column=1, columnspan=3, sticky="ew", padx=5, pady=5)

        buttons = ttk.Frame(form)
        buttons.grid(row=3, column=0, columnspan=4, sticky="w", padx=5, pady=5)
        ttk.Button(buttons, text="New / Clear", command=self.clear_balance_form).pack(side="left", padx=(0, 5))
        ttk.Button(buttons, text="Save Balance Entry", command=self.add_balance).pack(side="left", padx=5)
        for col in range(4):
            form.columnconfigure(col, weight=1)

        history = ttk.LabelFrame(self.balance_tab, text="Balance History", padding=10)
        history.pack(fill="both", expand=True)
        ttk.Label(history, text="Click a balance entry to load it for editing. Double-click a visit transaction to open that visit.").pack(anchor="w", pady=(0, 5))
        columns = ("id", "recorded", "actual", "type", "amount", "balance", "note")
        self.balance_tree = ttk.Treeview(history, columns=columns, show="headings", selectmode="browse")
        for col, heading, width in [
            ("id", "ID", 55), ("recorded", "Recorded Billing Date", 140), ("actual", "Actual Billing Date", 140),
            ("type", "Type", 120), ("amount", "Change", 110), ("balance", "Balance After", 120), ("note", "Note", 480)
        ]:
            self.balance_tree.heading(col, text=heading)
            self.balance_tree.column(col, width=width)
        scroll = ttk.Scrollbar(history, orient="vertical", command=self.balance_tree.yview)
        self.balance_tree.configure(yscrollcommand=scroll.set)
        self.balance_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.balance_tree.bind("<<TreeviewSelect>>", self.on_balance_selected)
        self.balance_tree.bind("<Double-1>", self.on_balance_double_click)

    @staticmethod
    def make_entry(parent):
        return ttk.Entry(parent)

    def make_history_combo(self, parent, field_name):
        combo = ttk.Combobox(parent, state="normal")
        combo._history_field_name = field_name
        return combo

    def load_visit_field_history(self):
        if not hasattr(self, "visit_reason"):
            return
        for widget in (self.visit_reason, self.treatment_modality, self.visit_duration, self.visit_subtotal, self.visit_total):
            field_name = getattr(widget, "_history_field_name", None)
            if not field_name:
                continue
            values = [row[0] for row in self.conn.execute(
                "SELECT value FROM visit_field_history WHERE field_name=? ORDER BY id DESC",
                (field_name,)
            ).fetchall()]
            widget["values"] = values

    def remember_visit_field_values(self, values_by_field):
        for field_name, value in values_by_field.items():
            value = str(value).strip()
            if not value:
                continue
            self.conn.execute(
                "INSERT OR IGNORE INTO visit_field_history (field_name, value) VALUES (?, ?)",
                (field_name, value)
            )


    # ---------------- Clients ----------------

    def clear_client_search(self):
        self.client_search_var.set("")
        self.client_search.focus_set()

    def load_clients(self):
        for item in self.client_tree.get_children():
            self.client_tree.delete(item)

        search = self.client_search_var.get().strip().casefold() if hasattr(self, "client_search_var") else ""
        rows = self.conn.execute(
            "SELECT id, username, legal_name, notes, balance FROM clients"
        ).fetchall()

        ranked = []
        for row in rows:
            client_id, username, legal_name, notes, balance = row
            username = username or ""
            legal_name = legal_name or ""
            notes = notes or ""

            if search:
                legal_pos = legal_name.casefold().find(search)
                username_pos = username.casefold().find(search)
                notes_pos = notes.casefold().find(search)

                # Only clients with a match in legal name, username, or notes are shown.
                if legal_pos == -1 and username_pos == -1 and notes_pos == -1:
                    continue

                # Priority: legal name, then username, then notes. Within a field,
                # earlier occurrences rank first.
                if legal_pos != -1:
                    rank = (0, legal_pos, legal_name.casefold(), username.casefold())
                elif username_pos != -1:
                    rank = (1, username_pos, legal_name.casefold(), username.casefold())
                else:
                    rank = (2, notes_pos, legal_name.casefold(), username.casefold())
            else:
                rank = (3, 0, legal_name.casefold(), username.casefold())

            ranked.append((rank, row))

        ranked.sort(key=lambda item: item[0])

        for _, row in ranked:
            client_id, username, legal_name, notes, balance = row
            self.client_tree.insert(
                "", "end", iid=str(client_id),
                values=(username, legal_name, self.format_money(balance), notes)
            )

    def on_client_selected(self, _event=None):
        selection = self.client_tree.selection()
        if not selection:
            return
        self.selected_client_id = int(selection[0])
        row = self.conn.execute("SELECT username, legal_name, address, phone, email, notes FROM clients WHERE id=?", (self.selected_client_id,)).fetchone()
        if not row:
            return
        for widget, value in zip((self.username, self.legal_name, self.address, self.phone, self.email), row[:5]):
            widget.delete(0, tk.END)
            widget.insert(0, value or "")
        self.client_notes.delete("1.0", tk.END)
        self.client_notes.insert("1.0", row[5] or "")
        self.load_visits()
        self.load_visit_selection()
        self.load_balance_history()

    def save_client(self):
        username = self.username.get().strip()
        legal_name = self.legal_name.get().strip()
        if not username or not legal_name:
            messagebox.showwarning("Missing Information", "Username and Legal Name are required.")
            return
        values = (username, legal_name, self.address.get().strip(), self.phone.get().strip(), self.email.get().strip(), self.client_notes.get("1.0", tk.END).strip())
        if self.selected_client_id:
            self.conn.execute("UPDATE clients SET username=?, legal_name=?, address=?, phone=?, email=?, notes=? WHERE id=?", values + (self.selected_client_id,))
        else:
            cur = self.conn.execute("INSERT INTO clients (username, legal_name, address, phone, email, notes) VALUES (?, ?, ?, ?, ?, ?)", values)
            self.selected_client_id = cur.lastrowid
        self.conn.commit()
        self.load_clients()
        self.load_visits()
        self.load_balance_history()
        messagebox.showinfo("Saved", "Client information saved.")

    def delete_client(self):
        if not self.selected_client_id:
            messagebox.showwarning("No Client", "Select a client first.")
            return
        if not messagebox.askyesno("Delete Client", "Delete this client and all visits and balance history?"):
            return
        self.conn.execute("DELETE FROM clients WHERE id=?", (self.selected_client_id,))
        self.conn.commit()
        self.clear_client_form()
        self.load_clients()
        self.load_visits()
        self.load_balance_history()

    def clear_client_form(self):
        self.selected_client_id = None
        self.selected_balance_transaction_id = None
        for widget in (self.username, self.legal_name, self.address, self.phone, self.email):
            widget.delete(0, tk.END)
        self.client_notes.delete("1.0", tk.END)
        self.clear_visit_form()
        self.clear_balance_form()
        self.visit_client_label.config(text="No client selected")
        self.selection_client_label.config(text="No client selected")
        self.balance_client_label.config(text="No client selected")
        self.current_balance_label.config(text="$0.00")
        self.load_visit_selection()

    # ---------------- Visits ----------------

    def load_visits(self):
        for item in self.visit_tree.get_children():
            self.visit_tree.delete(item)
        if not self.selected_client_id:
            self.visit_client_label.config(text="No client selected")
            return
        self.visit_client_label.config(text=self.get_client_name(self.selected_client_id))
        rows = self.conn.execute("""
            SELECT id, visit_date, reason, treatment_modality, duration, cost_subtotal, cost_total, billed, notes
            FROM visits WHERE client_id=? ORDER BY visit_date DESC, id DESC
        """, (self.selected_client_id,)).fetchall()
        for row in rows:
            self.visit_tree.insert("", "end", iid=str(row[0]), values=(
                row[1], row[2] or "", row[3] or "", row[4], self.format_money(row[5]),
                self.format_money(row[6]), "Yes" if row[7] else "No", row[8] or ""
            ))

    def load_visit_selection(self):
        """Load the selected client's visits into the independent multi-select tree."""
        for item in self.visit_selection_tree.get_children():
            self.visit_selection_tree.delete(item)

        if not self.selected_client_id:
            self.selection_client_label.config(text="No client selected")
            return

        self.selection_client_label.config(text=self.get_client_name(self.selected_client_id))
        rows = self.conn.execute("""
            SELECT id, visit_date, reason, treatment_modality, duration, cost_subtotal, cost_total, billed, notes
            FROM visits
            WHERE client_id=?
            ORDER BY visit_date DESC, id DESC
        """, (self.selected_client_id,)).fetchall()

        for row in rows:
            self.visit_selection_tree.insert("", "end", iid=str(row[0]), values=(
                row[1], row[2] or "", row[3] or "", row[4],
                self.format_money(row[5]), self.format_money(row[6]),
                "Yes" if row[7] else "No", row[8] or ""
            ))

    def save_visit(self):
        if not self.selected_client_id:
            messagebox.showwarning("No Client", "Select a client before saving a visit.")
            return
        visit_date = self.visit_date.get().strip()
        reason = self.visit_reason.get().strip()
        modality = self.treatment_modality.get().strip()
        try:
            duration_text = self.visit_duration.get().strip()
            duration = int(duration_text)
            if duration < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid Duration", "Duration must be a whole number (0 or greater).")
            return
        try:
            subtotal = self.parse_amount(self.visit_subtotal.get())
            total = self.parse_amount(self.visit_total.get())
        except ValueError:
            messagebox.showwarning("Invalid Cost", "Cost Subtotal and Cost Total must be valid numbers.")
            return
        notes = self.visit_notes.get("1.0", tk.END).strip()
        billed = 1 if self.visit_billed_var.get() else 0

        try:
            self.conn.execute("BEGIN")
            if self.selected_visit_id:
                old_total = self.conn.execute("SELECT cost_total FROM visits WHERE id=? AND client_id=?", (self.selected_visit_id, self.selected_client_id)).fetchone()
                if not old_total:
                    raise ValueError("The selected visit no longer exists.")
                self.conn.execute("""
                    UPDATE visits SET visit_date=?, reason=?, treatment_modality=?, duration=?, cost_subtotal=?, cost_total=?, billed=?, notes=?
                    WHERE id=? AND client_id=?
                """, (visit_date, reason, modality, duration, subtotal, total, billed, notes, self.selected_visit_id, self.selected_client_id))
                self.conn.execute("""
                    UPDATE balance_transactions
                    SET recorded_billing_date=?, actual_billing_date=?, amount=?, note=?
                    WHERE visit_id=?
                """, (visit_date, visit_date, -total, reason or "Visit charge", self.selected_visit_id))
            else:
                cur = self.conn.execute("""
                    INSERT INTO visits (client_id, visit_date, reason, treatment_modality, duration, cost_subtotal, cost_total, billed, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (self.selected_client_id, visit_date, reason, modality, duration, subtotal, total, billed, notes))
                self.selected_visit_id = cur.lastrowid
                self.conn.execute("""
                    INSERT INTO balance_transactions (client_id, recorded_billing_date, actual_billing_date, amount, note, transaction_type, visit_id)
                    VALUES (?, ?, ?, ?, ?, 'visit', ?)
                """, (self.selected_client_id, visit_date, visit_date, -total, reason or "Visit charge", self.selected_visit_id))
            self.remember_visit_field_values({
                "reason": reason,
                "treatment_modality": modality,
                "duration": duration,
                "cost_subtotal": f"{subtotal:.2f}",
                "cost_total": f"{total:.2f}",
            })
            self.recalculate_balance(self.selected_client_id)
            self.conn.commit()
        except Exception as exc:
            self.conn.rollback()
            messagebox.showerror("Error Saving Visit", f"The visit could not be saved.\n\n{exc}")
            return

        self.load_visit_field_history()
        self.load_clients()
        self.load_visits()
        self.load_visit_selection()
        self.load_balance_history()
        self.clear_visit_form()
        messagebox.showinfo("Saved", "Visit saved and balance updated.")

    def clear_visit_form(self):
        self.selected_visit_id = None
        self.visit_date.set(date.today().strftime(DATE_FORMAT))
        for widget in (self.visit_reason, self.treatment_modality, self.visit_duration, self.visit_subtotal, self.visit_total):
            widget.delete(0, tk.END)
        self.visit_duration.insert(0, "0")
        self.visit_subtotal.insert(0, "0.00")
        self.visit_total.insert(0, "0.00")
        self.visit_billed_var.set(False)
        self.visit_notes.delete("1.0", tk.END)

    def on_visit_selected(self, _event=None):
        selection = self.visit_tree.selection()
        if not selection:
            return
        self.load_visit_into_form(int(selection[0]))

    def on_visit_double_click(self, _event=None):
        selection = self.visit_tree.selection()
        if not selection:
            return
        self.load_visit_into_form(int(selection[0]))
        self.notebook.select(self.visits_tab)

    def load_visit_into_form(self, visit_id):
        if not self.selected_client_id:
            return
        row = self.conn.execute("""
            SELECT visit_date, reason, treatment_modality, duration, cost_subtotal, cost_total, billed, notes
            FROM visits WHERE id=? AND client_id=?
        """, (visit_id, self.selected_client_id)).fetchone()
        if not row:
            return
        self.selected_visit_id = visit_id
        self.visit_date.set(row[0])
        self.visit_reason.delete(0, tk.END); self.visit_reason.insert(0, row[1] or "")
        self.treatment_modality.delete(0, tk.END); self.treatment_modality.insert(0, row[2] or "")
        self.visit_duration.delete(0, tk.END); self.visit_duration.insert(0, str(row[3] or 0))
        self.visit_subtotal.delete(0, tk.END); self.visit_subtotal.insert(0, f"{row[4]:.2f}")
        self.visit_total.delete(0, tk.END); self.visit_total.insert(0, f"{row[5]:.2f}")
        self.visit_billed_var.set(bool(row[6]))
        self.visit_notes.delete("1.0", tk.END); self.visit_notes.insert("1.0", row[7] or "")

    # ---------------- Receipts ----------------

    def open_receipt_dialog(self):
        if not self.selected_client_id:
            messagebox.showwarning("No Client", "Select a client before generating a receipt.")
            return

        selected = self.visit_selection_tree.selection()
        if not selected:
            messagebox.showwarning("No Visits Selected", "Select one or more visits from the Visit Selection module first.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Generate Receipt")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="File Name:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        file_var = tk.StringVar(value=f"receipt_{date.today().isoformat()}")
        file_entry = ttk.Entry(frame, textvariable=file_var, width=40)
        file_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame, text="Health Issue:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        health_var = tk.StringVar()
        health_entry = ttk.Entry(frame, textvariable=health_var, width=40)
        health_entry.grid(row=1, column=1, padx=5, pady=5)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))

        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="right", padx=(5, 0))

        def confirm():
            file_name = file_var.get().strip()
            health_issue = health_var.get().strip()

            if not file_name:
                messagebox.showwarning("Missing File Name", "Enter a file name.", parent=dialog)
                return
            if not health_issue:
                messagebox.showwarning("Missing Health Issue", "Enter the health issue.", parent=dialog)
                return

            if not file_name.lower().endswith(".pdf"):
                file_name += ".pdf"

            try:
                receipt = self.build_receipt_data(selected, health_issue)
            except ValueError as exc:
                messagebox.showwarning("Cannot Generate Receipt", str(exc), parent=dialog)
                return

            print("Receipt file name:", file_name)
            print("Receipt data:")
            print(receipt)
            print()

            dialog.destroy()

            loading = tk.Toplevel(self.root)
            loading.title("Loading")
            loading.geometry("300x120")
            loading.resizable(False, False)
            loading.transient(self.root)
            loading.grab_set()

            label = tk.Label(loading, text="Loading, please wait...", font=("Arial", 12))
            label.pack(expand=True)
            loading.update()

            try:
                generate_receipt(receipt, file_name)
            except Exception as exc:
                loading.grab_release()
                loading.destroy()
                messagebox.showerror("Receipt Generation Failed", str(exc), parent=self.root)
                return

            loading.grab_release()
            loading.destroy()
            messagebox.showinfo(
                "Loaded Successfully",
                "The data has been loaded successfully!",
                parent=self.root
            )

        ttk.Button(button_frame, text="Confirm", command=confirm).pack(side="right")
        file_entry.focus_set()

    def build_receipt_data(self, selected_items, health_issue):
        client = self.conn.execute(
            "SELECT legal_name, address FROM clients WHERE id=?",
            (self.selected_client_id,)
        ).fetchone()

        if not client:
            raise ValueError("The selected client no longer exists.")

        visits = []
        total_cost = 0.0

        for item_id in selected_items:
            visit = self.conn.execute("""
                SELECT visit_date, treatment_modality, duration, cost_subtotal
                FROM visits
                WHERE id=? AND client_id=?
            """, (int(item_id), self.selected_client_id)).fetchone()

            if not visit:
                continue

            visit_date = date.fromisoformat(visit[0])
            subtotal = float(visit[3])
            total_cost += subtotal

            if not subtotal.is_integer():
                raise ValueError(
                    f"Visit on {visit[0]} has a subtotal of {subtotal:.2f}. "
                    "The receipt format requires each visit cost to be an integer."
                )

            visits.append({
                "year": visit_date.year,
                "month": visit_date.month,
                "day": visit_date.day,
                "modality": visit[1] or "",
                "duration": int(visit[2]),
                "cost": int(subtotal),
            })

        if not visits:
            raise ValueError("No valid visits were found for the selected client.")

        return {
            "name": client[0] or "",
            "address": client[1] or "",
            "health_issue": health_issue,
            "cost": total_cost,
            "date": date.today(),
            "visits": visits,
        }

    # ---------------- Balance ----------------

    def add_balance(self):
        if not self.selected_client_id:
            messagebox.showwarning("No Client", "Select a client before saving a balance entry.")
            return

        recorded = self.balance_recorded_date.get().strip()
        actual = self.balance_actual_date.get().strip()
        try:
            amount = self.parse_amount(self.balance_amount.get())
        except ValueError:
            messagebox.showwarning("Invalid Amount", "Amount must be a valid number. Negative values are allowed.")
            return
        if amount == 0:
            messagebox.showwarning("Invalid Amount", "Amount cannot be zero.")
            return

        note = self.balance_note.get("1.0", tk.END).strip()

        try:
            self.conn.execute("BEGIN")

            if self.selected_balance_transaction_id:
                row = self.conn.execute("""
                    SELECT id, transaction_type, visit_id
                    FROM balance_transactions
                    WHERE id=? AND client_id=?
                """, (self.selected_balance_transaction_id, self.selected_client_id)).fetchone()

                if not row:
                    raise ValueError("The selected balance entry no longer exists.")
                if row[1] == "visit" or row[2] is not None:
                    raise ValueError("Visit charges cannot be edited as balance entries. Edit the visit instead.")

                self.conn.execute("""
                    UPDATE balance_transactions
                    SET recorded_billing_date=?, actual_billing_date=?, amount=?, note=?
                    WHERE id=? AND client_id=?
                """, (recorded, actual or None, amount, note, self.selected_balance_transaction_id, self.selected_client_id))
            else:
                self.conn.execute("""
                    INSERT INTO balance_transactions
                    (client_id, recorded_billing_date, actual_billing_date, amount, note, transaction_type)
                    VALUES (?, ?, ?, ?, ?, 'balance')
                """, (self.selected_client_id, recorded, actual or None, amount, note))

            self.recalculate_balance(self.selected_client_id)
            self.conn.commit()
        except Exception as exc:
            self.conn.rollback()
            messagebox.showerror("Error Saving Balance", f"The balance entry could not be saved.\n\n{exc}")
            return

        self.load_clients()
        self.load_balance_history()
        self.clear_balance_form()
        messagebox.showinfo("Balance Updated", "The balance entry has been saved and the client's balance updated.")

    def load_balance_history(self):
        self.balance_tree.selection_remove(self.balance_tree.selection())
        for item in self.balance_tree.get_children():
            self.balance_tree.delete(item)
        if not self.selected_client_id:
            self.balance_client_label.config(text="No client selected")
            self.current_balance_label.config(text="$0.00")
            return

        balance = self.get_current_balance(self.selected_client_id)
        self.balance_client_label.config(text=self.get_client_name(self.selected_client_id))
        self.current_balance_label.config(text=self.format_money(balance))

        rows = self.conn.execute("""
            SELECT id, recorded_billing_date, actual_billing_date, transaction_type, amount, note, visit_id
            FROM balance_transactions
            WHERE client_id=?
            ORDER BY COALESCE(actual_billing_date, recorded_billing_date) DESC, id DESC
        """, (self.selected_client_id,)).fetchall()

        running = balance
        for row in rows:
            transaction_id, recorded, actual, tx_type, amount, note, visit_id = row
            self.balance_tree.insert("", "end", iid=str(transaction_id), values=(
                transaction_id, recorded or "", actual or "", self.transaction_label(tx_type, amount),
                self.format_signed_money(amount), self.format_money(running), note or ""
            ), tags=(str(visit_id or 0),))
            running -= float(amount)

    def on_balance_selected(self, _event=None):
        selection = self.balance_tree.selection()
        if not selection:
            return

        transaction_id = int(selection[0])
        row = self.conn.execute("""
            SELECT transaction_type, visit_id
            FROM balance_transactions
            WHERE id=? AND client_id=?
        """, (transaction_id, self.selected_client_id)).fetchone()

        if not row:
            return

        tx_type, visit_id = row
        if tx_type == "visit" or visit_id is not None:
            # Visit transactions are edited through the visit form.
            self.selected_balance_transaction_id = None
            return

        self.load_balance_into_form(transaction_id)

    def load_balance_into_form(self, transaction_id):
        if not self.selected_client_id:
            return

        row = self.conn.execute("""
            SELECT recorded_billing_date, actual_billing_date, amount, note, transaction_type, visit_id
            FROM balance_transactions
            WHERE id=? AND client_id=?
        """, (transaction_id, self.selected_client_id)).fetchone()

        if not row:
            return
        if row[4] == "visit" or row[5] is not None:
            return

        self.selected_balance_transaction_id = transaction_id
        self.balance_recorded_date.set(row[0])
        self.balance_actual_date.set(row[1] or row[0])
        self.balance_amount.delete(0, tk.END)
        self.balance_amount.insert(0, f"{row[2]:.2f}")
        self.balance_note.delete("1.0", tk.END)
        self.balance_note.insert("1.0", row[3] or "")

    def on_balance_double_click(self, _event=None):
        selection = self.balance_tree.selection()
        if not selection:
            return

        transaction_id = int(selection[0])
        row = self.conn.execute("""
            SELECT transaction_type, visit_id
            FROM balance_transactions
            WHERE id=? AND client_id=?
        """, (transaction_id, self.selected_client_id)).fetchone()

        if not row:
            return

        tx_type, visit_id = row
        if visit_id is not None:
            self.load_visit_into_form(visit_id)
            self.notebook.select(self.visits_tab)

    def clear_balance_form(self):
        self.selected_balance_transaction_id = None
        today = date.today().strftime(DATE_FORMAT)
        self.balance_recorded_date.set(today)
        self.balance_actual_date.set(today)
        self.balance_amount.delete(0, tk.END)
        self.balance_note.delete("1.0", tk.END)

    # ---------------- Helpers ----------------

    def get_client_name(self, client_id):
        row = self.conn.execute("SELECT username, legal_name FROM clients WHERE id=?", (client_id,)).fetchone()
        if not row:
            return "Unknown Client"
        return f"{row[0]} — {row[1]}" if row[0] and row[1] else (row[0] or row[1] or "Unnamed Client")

    def get_current_balance(self, client_id):
        row = self.conn.execute("SELECT COALESCE(SUM(amount), 0) FROM balance_transactions WHERE client_id=?", (client_id,)).fetchone()
        return float(row[0] or 0)

    def recalculate_balance(self, client_id):
        self.conn.execute("""
            UPDATE clients SET balance=(SELECT COALESCE(SUM(amount),0) FROM balance_transactions WHERE client_id=?) WHERE id=?
        """, (client_id, client_id))

    @staticmethod
    def parse_amount(value):
        return round(float(value.strip().replace("$", "").replace(",", "")), 2)

    @staticmethod
    def format_money(amount):
        return f"${float(amount):,.2f}"

    @staticmethod
    def format_signed_money(amount):
        amount = float(amount)
        if amount > 0:
            return f"+${amount:,.2f}"
        if amount < 0:
            return f"-${abs(amount):,.2f}"
        return "$0.00"

    @staticmethod
    def transaction_label(tx_type, amount):
        if tx_type == "visit":
            return "Visit"
        return "Balance Added" if float(amount) > 0 else "Balance Decreased"

    def close(self):
        self.conn.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ClientApp(root)
    root.mainloop()
