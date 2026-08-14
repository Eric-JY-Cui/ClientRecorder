import importlib.util
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path

APP_PATH = Path(__file__).with_name('client_records_app.py')

# v10 imports receipt_generator. Stub it so the unit tests do not require the
# user's external receipt generator implementation to be installed.
receipt_stub = types.ModuleType('receipt_generator')
receipt_stub.generate_receipt = lambda *args, **kwargs: None
sys.modules['receipt_generator'] = receipt_stub

spec = importlib.util.spec_from_file_location('client_records_v10', APP_PATH)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
ClientApp = app.ClientApp


class FakeVar:
    def __init__(self, value=''):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeEntry:
    def __init__(self, value=''):
        self.value = value
        self._history_field_name = None

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def delete(self, *_):
        self.value = ''

    def insert(self, *_args):
        self.value = _args[-1]

    def __setitem__(self, key, value):
        if key == 'values':
            self.values = list(value)


class FakeText(FakeEntry):
    def get(self, *_):
        return self.value + '\n'

    def delete(self, *_):
        self.value = ''


class FakeTree:
    def __init__(self):
        self.items = {}
        self.selected = []
        self.inserted = []

    def get_children(self):
        return list(self.items)

    def delete(self, item):
        self.items.pop(item, None)

    def insert(self, _parent, _index, iid=None, values=(), tags=()):
        iid = str(iid if iid is not None else len(self.items) + 1)
        self.items[iid] = {'values': tuple(values), 'tags': tuple(tags)}
        self.inserted.append((iid, tuple(values), tuple(tags)))
        return iid

    def selection(self):
        return tuple(self.selected)

    def selection_remove(self, _selection):
        self.selected = []


class ClientRecordsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp.close()
        self.app = object.__new__(ClientApp)
        self.app.conn = sqlite3.connect(self.tmp.name)
        self.app.conn.execute('PRAGMA foreign_keys = ON')
        self.app.create_tables()

    def tearDown(self):
        self.app.conn.close()
        Path(self.tmp.name).unlink(missing_ok=True)

    def add_client(self, username='user1', legal_name='John Smith', address='123 Main St', notes='note'):
        cur = self.app.conn.execute(
            'INSERT INTO clients (username, legal_name, address, notes) VALUES (?, ?, ?, ?)',
            (username, legal_name, address, notes),
        )
        self.app.conn.commit()
        return cur.lastrowid

    def add_visit(self, client_id, visit_date='2026-08-01', reason='Initial', modality='Manual', duration=45,
                  subtotal=100.0, total=80.0, billed=1, notes='visit note'):
        cur = self.app.conn.execute('''
            INSERT INTO visits
            (client_id, visit_date, reason, treatment_modality, duration,
             cost_subtotal, cost_total, billed, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (client_id, visit_date, reason, modality, duration, subtotal, total, billed, notes))
        visit_id = cur.lastrowid
        self.app.conn.execute('''
            INSERT INTO balance_transactions
            (client_id, recorded_billing_date, actual_billing_date, amount, note, transaction_type, visit_id)
            VALUES (?, ?, ?, ?, ?, 'visit', ?)
        ''', (client_id, visit_date, visit_date, -total, reason, visit_id))
        self.app.conn.commit()
        return visit_id

    def add_balance(self, client_id, amount, recorded='2026-08-02', actual='2026-08-03', note='billing'):
        cur = self.app.conn.execute('''
            INSERT INTO balance_transactions
            (client_id, recorded_billing_date, actual_billing_date, amount, note, transaction_type)
            VALUES (?, ?, ?, ?, ?, 'balance')
        ''', (client_id, recorded, actual, amount, note))
        self.app.recalculate_balance(client_id)
        self.app.conn.commit()
        return cur.lastrowid

    def test_schema_contains_all_required_tables_and_fields(self):
        tables = {r[0] for r in self.app.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        self.assertTrue({'clients', 'visits', 'balance_transactions', 'visit_field_history'}.issubset(tables))

        client_cols = {r[1] for r in self.app.conn.execute('PRAGMA table_info(clients)')}
        visit_cols = {r[1] for r in self.app.conn.execute('PRAGMA table_info(visits)')}
        balance_cols = {r[1] for r in self.app.conn.execute('PRAGMA table_info(balance_transactions)')}
        self.assertTrue({'username', 'legal_name', 'address', 'phone', 'email', 'notes', 'balance'}.issubset(client_cols))
        self.assertTrue({'visit_date', 'reason', 'treatment_modality', 'duration', 'cost_subtotal', 'cost_total', 'billed', 'notes'}.issubset(visit_cols))
        self.assertTrue({'recorded_billing_date', 'actual_billing_date', 'amount', 'note', 'transaction_type', 'visit_id'}.issubset(balance_cols))

    def test_client_create_and_note_field_is_distinct_from_email(self):
        client_id = self.add_client(notes='This is the real note')
        self.app.conn.execute('UPDATE clients SET email=?, phone=? WHERE id=?', ('john@example.com', '555-1234', client_id))
        self.app.conn.commit()
        row = self.app.conn.execute('SELECT email, notes FROM clients WHERE id=?', (client_id,)).fetchone()
        self.assertEqual(row, ('john@example.com', 'This is the real note'))

    def test_client_search_prioritizes_legal_name_then_username_then_notes(self):
        first = self.add_client('match_user', 'Zebra Patient', notes='match in note')
        second = self.add_client('other_user', 'Match Patient', notes='none')
        third = self.add_client('other_user', 'Beta Patient', notes='match in note')

        class SearchApp: pass
        fake = object.__new__(ClientApp)
        fake.conn = self.app.conn
        fake.client_tree = FakeTree()
        fake.client_search_var = FakeVar('match')
        fake.load_clients()

        # Legal-name match first, username match second, notes match third.
        self.assertEqual([x[0] for x in fake.client_tree.inserted], [str(second), str(first), str(third)])

    def test_positive_balance_increases_balance(self):
        client_id = self.add_client()
        self.add_balance(client_id, 100.0)
        self.assertEqual(self.app.get_current_balance(client_id), 100.0)

    def test_negative_balance_decreases_balance(self):
        client_id = self.add_client()
        self.add_balance(client_id, 100.0)
        self.add_balance(client_id, -35.0)
        self.assertEqual(self.app.get_current_balance(client_id), 65.0)

    def test_visit_cost_creates_negative_balance_transaction(self):
        client_id = self.add_client()
        visit_id = self.add_visit(client_id, total=80.0)
        tx = self.app.conn.execute(
            'SELECT amount, transaction_type, visit_id FROM balance_transactions WHERE visit_id=?',
            (visit_id,)
        ).fetchone()
        self.assertEqual(tx, (-80.0, 'visit', visit_id))
        self.assertEqual(self.app.get_current_balance(client_id), -80.0)

    def test_editing_a_visit_updates_its_balance_transaction(self):
        client_id = self.add_client()
        visit_id = self.add_visit(client_id, total=80.0)
        self.app.conn.execute(
            'UPDATE visits SET cost_total=? WHERE id=?', (120.0, visit_id)
        )
        self.app.conn.execute(
            'UPDATE balance_transactions SET amount=? WHERE visit_id=?', (-120.0, visit_id)
        )
        self.app.recalculate_balance(client_id)
        self.app.conn.commit()
        self.assertEqual(self.app.get_current_balance(client_id), -120.0)
        self.assertEqual(
            self.app.conn.execute('SELECT amount FROM balance_transactions WHERE visit_id=?', (visit_id,)).fetchone()[0],
            -120.0,
        )

    def test_balance_edit_recalculates_client_balance(self):
        client_id = self.add_client()
        tx_id = self.add_balance(client_id, 100.0)
        self.app.conn.execute('UPDATE balance_transactions SET amount=? WHERE id=?', (250.0, tx_id))
        self.app.recalculate_balance(client_id)
        self.app.conn.commit()
        self.assertEqual(self.app.get_current_balance(client_id), 250.0)

    def test_visit_field_history_deduplicates_values(self):
        self.app.remember_visit_field_values({
            'reason': 'Initial',
            'treatment_modality': 'Manual Therapy',
            'duration': 45,
            'cost_subtotal': '100.00',
            'cost_total': '80.00',
        })
        self.app.remember_visit_field_values({
            'reason': 'Initial',
            'treatment_modality': 'Manual Therapy',
            'duration': 45,
            'cost_subtotal': '100.00',
            'cost_total': '80.00',
        })
        counts = dict(self.app.conn.execute(
            'SELECT field_name, COUNT(*) FROM visit_field_history GROUP BY field_name'
        ).fetchall())
        self.assertEqual(counts, {
            'reason': 1,
            'treatment_modality': 1,
            'duration': 1,
            'cost_subtotal': 1,
            'cost_total': 1,
        })

    def test_receipt_data_matches_required_structure(self):
        client_id = self.add_client(address='123 Main St')
        v1 = self.add_visit(client_id, '2026-07-01', modality='Manual Therapy', duration=30, subtotal=100.0, total=90.0)
        v2 = self.add_visit(client_id, '2026-07-15', modality='Exercise', duration=45, subtotal=150.0, total=120.0)
        fake = object.__new__(ClientApp)
        fake.conn = self.app.conn
        fake.selected_client_id = client_id
        receipt = fake.build_receipt_data([str(v1), str(v2)], 'Back pain')

        self.assertEqual(receipt['name'], 'John Smith')
        self.assertEqual(receipt['address'], '123 Main St')
        self.assertEqual(receipt['health_issue'], 'Back pain')
        self.assertEqual(receipt['cost'], 250.0)
        self.assertEqual(receipt['date'], date.today())
        self.assertEqual(receipt['visits'], [
            {'year': 2026, 'month': 7, 'day': 1, 'modality': 'Manual Therapy', 'duration': 30, 'cost': 100},
            {'year': 2026, 'month': 7, 'day': 15, 'modality': 'Exercise', 'duration': 45, 'cost': 150},
        ])

    def test_receipt_data_rejects_non_integer_subtotal(self):
        client_id = self.add_client()
        visit_id = self.add_visit(client_id, subtotal=99.50)
        fake = object.__new__(ClientApp)
        fake.conn = self.app.conn
        fake.selected_client_id = client_id
        with self.assertRaises(ValueError):
            fake.build_receipt_data([str(visit_id)], 'Issue')

    def test_receipt_skips_nonexistent_visit_and_errors_when_none_remain(self):
        client_id = self.add_client()
        fake = object.__new__(ClientApp)
        fake.conn = self.app.conn
        fake.selected_client_id = client_id
        with self.assertRaises(ValueError):
            fake.build_receipt_data(['999999'], 'Issue')

    def test_formatting_and_amount_parsing(self):
        self.assertEqual(ClientApp.parse_amount('$1,234.56'), 1234.56)
        self.assertEqual(ClientApp.parse_amount(' -25.5 '), -25.5)
        self.assertEqual(ClientApp.format_money(-25), '$-25.00')
        self.assertEqual(ClientApp.format_signed_money(25), '+$25.00')
        self.assertEqual(ClientApp.format_signed_money(-25), '-$25.00')
        self.assertEqual(ClientApp.transaction_label('balance', 50), 'Balance Added')
        self.assertEqual(ClientApp.transaction_label('balance', -50), 'Balance Decreased')
        self.assertEqual(ClientApp.transaction_label('visit', -50), 'Visit')

    def test_single_click_visit_selection_can_load_visit_for_edit(self):
        client_id = self.add_client()
        visit_id = self.add_visit(client_id)
        fake = object.__new__(ClientApp)
        fake.conn = self.app.conn
        fake.selected_client_id = client_id
        fake.selected_visit_id = None
        fake.visit_date = FakeEntry()
        fake.visit_reason = FakeEntry()
        fake.treatment_modality = FakeEntry()
        fake.visit_duration = FakeEntry()
        fake.visit_subtotal = FakeEntry()
        fake.visit_total = FakeEntry()
        fake.visit_notes = FakeText()
        fake.visit_billed_var = FakeVar(False)
        fake.load_visit_into_form(visit_id)
        self.assertEqual(fake.selected_visit_id, visit_id)
        self.assertEqual(fake.visit_reason.get(), 'Initial')
        self.assertEqual(fake.treatment_modality.get(), 'Manual')
        self.assertEqual(fake.visit_duration.get(), '45')
        self.assertEqual(fake.visit_subtotal.get(), '100.00')
        self.assertEqual(fake.visit_total.get(), '80.00')

    def test_single_click_balance_selection_loads_balance_only_not_visit(self):
        client_id = self.add_client()
        balance_id = self.add_balance(client_id, 75.0)
        fake = object.__new__(ClientApp)
        fake.conn = self.app.conn
        fake.selected_client_id = client_id
        fake.selected_balance_transaction_id = None
        fake.balance_recorded_date = FakeEntry()
        fake.balance_actual_date = FakeEntry()
        fake.balance_amount = FakeEntry()
        fake.balance_note = FakeText()
        fake.load_balance_into_form(balance_id)
        self.assertEqual(fake.selected_balance_transaction_id, balance_id)
        self.assertEqual(fake.balance_amount.get(), '75.00')

    def test_visit_transaction_is_not_loaded_as_editable_balance(self):
        client_id = self.add_client()
        visit_id = self.add_visit(client_id)
        tx_id = self.app.conn.execute('SELECT id FROM balance_transactions WHERE visit_id=?', (visit_id,)).fetchone()[0]
        fake = object.__new__(ClientApp)
        fake.conn = self.app.conn
        fake.selected_client_id = client_id
        fake.selected_balance_transaction_id = None
        # Calling the underlying loader directly should refuse visit transactions.
        fake.balance_recorded_date = FakeEntry('')
        fake.balance_actual_date = FakeEntry('')
        fake.balance_amount = FakeEntry('')
        fake.balance_note = FakeText('')
        fake.load_balance_into_form(tx_id)
        self.assertIsNone(fake.selected_balance_transaction_id)

    def test_cascade_delete_removes_visits_and_balance_transactions(self):
        client_id = self.add_client()
        visit_id = self.add_visit(client_id)
        self.add_balance(client_id, 25.0)
        self.app.conn.execute('DELETE FROM clients WHERE id=?', (client_id,))
        self.app.conn.commit()
        self.assertIsNone(self.app.conn.execute('SELECT 1 FROM visits WHERE id=?', (visit_id,)).fetchone())
        self.assertEqual(self.app.conn.execute('SELECT COUNT(*) FROM balance_transactions WHERE client_id=?', (client_id,)).fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
