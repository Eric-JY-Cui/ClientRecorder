# Client Records Application

A desktop client-record management application built with **Python**, **Tkinter**, and **SQLite**.

The application is currently at **v10** and is designed as a foundation that can be extended with additional client, visit, billing, and reporting functionality.

## Features

### Client management

Each client can have the following information:

- Username
- Legal Name
- Address
- Phone
- Email
- Note

The Clients section provides:

- Create a new client
- Edit an existing client
- Delete a client
- Search clients
- View the client's current balance

The client list displays:

- Username
- Legal Name
- Balance
- Note


### Client search

The search box filters clients when the search text appears in any of these fields:

1. Legal Name
2. Username
3. Note

Search results are prioritized in that order. The search is case-insensitive.

### Visits

Each visit contains:

- Visit Date
- Reason
- Treatment Modality
- Duration
- Cost Subtotal
- Cost Total
- Billed
- Note

Dates are selected using a calendar/date-picker control rather than being typed manually.

`Duration` is stored as an integer.

`Cost Subtotal` is the visit's subtotal and is used when generating receipts.

`Cost Total` is the amount charged against the client's balance.

`Billed` is stored as a checkmark/boolean value.

Visits can be selected individually for editing. A single click loads the selected visit into the edit form.

### Visit selection for batch operations

A separate Visit Selection section allows multiple visits to be selected at once.

This is intentionally separate from the normal visit-editing list so that batch operations can be added without changing the single-visit editing workflow.

The current batch operation is receipt generation.

### Receipt generation

The system can automatically generate formated receipts and convert it to pdf version. 

A receipt template is used to structure the format of the receipt, and values are inputed by the system and converts to pdf. 

The pdf version of the receipt is placed. 

### Visit field history

The following visit fields remember previous entries:

- Reason
- Treatment Modality
- Duration
- Cost Subtotal
- Cost Total

These values are shown in editable dropdowns when entering a new visit.

The history is stored in the SQLite database and is shared across clients. Duplicate history values are avoided.

### Balance tracking

Each client has a current balance and a balance history.

A balance entry contains:

- Recorded Billing Date
- Actual Billing Date
- Amount
- Note

Dates use the calendar/date-picker control.

Balance amounts can be either positive or negative:

- Positive amount → increases the client's balance
- Negative amount → decreases the client's balance

Balance entries can be edited. Selecting a balance entry with a single click loads it into the balance form for editing.

### Visit charges and balance history

Saving a visit creates a corresponding balance transaction using the visit's **Cost Total**.

For example:

- Balance addition: `+100.00`
- Visit charge: `-40.00`
- Current balance: `60.00`

Visit transactions appear in the client's balance history and remain linked to their originating visit.

Double-clicking a visit transaction in balance history opens the corresponding visit information.

The balance can become negative.

### Receipt generation

The application supports receipt generation through an external module named `receipt_generator`.

The application imports:

```python
from receipt_generator import generate_receipt
```

The current receipt workflow is:

1. Select multiple visits in the Visit Selection section.
2. Press **Generate Receipt**.
3. Enter the PDF file name.
4. Enter the health issue to appear on the receipt.
5. Confirm.
6. The application builds the receipt dictionary.
7. `generate_receipt(receipt, file_name)` is called to create the PDF.

The file name automatically receives `.pdf` if the user does not provide the extension.

## Database

The application uses SQLite and stores its data in:

```text
client_records.db
```

No database server is required.

The current schema contains these main tables:

### `clients`

Stores basic client information and the current balance.

### `visits`

Stores visit records and links each visit to a client.

### `balance_transactions`

Stores balance additions, balance decreases, and visit-related charges.

### `visit_field_history`

Stores reusable values for the visit dropdown fields.

The application is currently intended to start with a fresh database schema. Database migration support is intentionally not included.

## Requirements

- Python 3
- Tkinter
- SQLite3 (included with the standard Python installation)
- The project's `receipt_generator.py` module for PDF receipt generation

On most Python installations, Tkinter is included. On some Linux distributions it must be installed separately through the operating system package manager.

