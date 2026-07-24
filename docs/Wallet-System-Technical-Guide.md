# Wallet System - Technical Documentation

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Data Flow](#data-flow)
4. [Configuration Options](#configuration-options)
5. [Doctypes](#doctypes)
6. [API Reference](#api-reference)
7. [Hooks & Triggers](#hooks--triggers)
8. [Setup Guide](#setup-guide)
9. [GL Entries](#gl-entries)

---

## System Overview

The Wallet & Loyalty System provides customers with:
- **Loyalty Points**: Earned on every purchase based on collection rules
- **Wallet Balance**: Points automatically converted to spendable credit
- **Wallet Payment**: Use wallet balance to pay at POS

### Key Principle

**Enable Loyalty Program** is the master switch. When enabled:
- Loyalty Program selection is **mandatory**
- Wallet Account selection is **mandatory**
- Auto Create Wallet is **always enabled** (read-only)
- Convert Loyalty Points to Wallet is **always enabled** (read-only)

```
Loyalty Program Enabled → All wallet features automatically activated
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         POS NEXT WALLET SYSTEM                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐     ┌─────────────────┐     ┌───────────────────┐     │
│  │   Customer  │────▶│     Wallet      │────▶│ Wallet Transaction│     │
│  └─────────────┘     └─────────────────┘     └───────────────────┘     │
│         │                    │                        │                 │
│         │                    │                        │                 │
│         ▼                    ▼                        ▼                 │
│  ┌─────────────┐     ┌─────────────────┐     ┌───────────────────┐     │
│  │  Loyalty    │     │   GL Account    │     │    GL Entries     │     │
│  │  Program    │     │ (Receivable)    │     │                   │     │
│  └─────────────┘     └─────────────────┘     └───────────────────┘     │
│         │                                                               │
│         ▼                                                               │
│  ┌─────────────┐                                                        │
│  │  Loyalty    │  ◄── Created by ERPNext on invoice submit              │
│  │Point Entry  │                                                        │
│  └─────────────┘                                                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### File Structure

```
pos_next/
├── pos_next/
│   ├── api/
│   │   ├── wallet.py              # Main wallet API
│   │   └── customers.py           # Customer hooks (loyalty assignment)
│   └── doctype/
│       ├── wallet/                # Wallet doctype
│       │   ├── wallet.py
│       │   └── wallet.json
│       ├── wallet_transaction/    # Transaction doctype
│       │   ├── wallet_transaction.py
│       │   └── wallet_transaction.json
│       └── pos_settings/          # Configuration
│           ├── pos_settings.py
│           └── pos_settings.json
├── hooks.py                       # Document event hooks
```

---

## Data Flow

### Flow 1: Loyalty Points → Wallet

```
1. Customer makes purchase
   │
   ▼
2. Sales Invoice submitted
   │
   ├──▶ ERPNext creates Loyalty Point Entry (automatic)
   │    └── Based on Loyalty Program Collection Rules
   │
   └──▶ process_loyalty_to_wallet() hook triggered
        │
        ├── Check: enable_loyalty_program = 1?
        ├── Check: loyalty_to_wallet = 1? (always true when loyalty enabled)
        ├── Check: Customer has loyalty_program?
        │
        ▼
3. Get loyalty points from Loyalty Point Entry
   │
   ▼
4. Get conversion_factor from Loyalty Program
   │
   ▼
5. Calculate: credit_amount = points × conversion_factor
   │
   ▼
6. Create Wallet Transaction (Credit, source_type="Loyalty Program")
   │
   ▼
7. GL Entries created:
   - Debit: Expense Account (Loyalty)
   - Credit: Wallet Account (Customer party)
```

### Flow 2: Wallet Payment

```
1. Customer selects "Redeem Points" payment method in POS
   │
   ▼
2. Sales Invoice created with wallet payment
   │
   ▼
3. validate_wallet_payment() hook triggered
   │
   ├── Get wallet balance from GL
   ├── Check: payment_amount ≤ wallet_balance?
   │
   ▼
4. Invoice submitted
   │
   ▼
5. Payment Entry / GL Entries created:
   - Debit: Wallet Account (reduces customer credit)
   - Credit: Revenue Account
```

### Flow 3: Manual Credit

```
1. Admin creates Wallet Transaction manually
   │
   ▼
2. Select: transaction_type = "Credit"
   │
   ▼
3. Select: source_type = "Manual Adjustment" / "Refund"
   │
   ▼
4. Submit transaction
   │
   ▼
5. GL Entries created:
   - Debit: Expense/Refund Account
   - Credit: Wallet Account (Customer party)
```

---

## Configuration Options

### POS Settings - Wallet & Loyalty Section

| Field | Type | Mandatory | Description |
|-------|------|-----------|-------------|
| `enable_loyalty_program` | Check | No | **Master switch** - enables all loyalty/wallet features |
| `default_loyalty_program` | Link (Loyalty Program) | **Yes*** | Loyalty program for this POS profile |
| `wallet_account` | Link (Account) | **Yes*** | Receivable account for wallet balances |
| `auto_create_wallet` | Check | Read-only | Always enabled when loyalty is on |
| `loyalty_to_wallet` | Check | Read-only | Always enabled when loyalty is on |

> *Mandatory when `enable_loyalty_program` is checked

### Field Behavior When Loyalty Enabled

| Field | Visibility | Editable | Default |
|-------|------------|----------|---------|
| Loyalty Program | Visible | Yes | Required |
| Wallet Account | Visible | Yes | Required |
| Auto Create Wallet | Visible | **No** (read-only) | Always ✓ |
| Convert to Wallet | Visible | **No** (read-only) | Always ✓ |

### Mode of Payment

| Field | Type | Description |
|-------|------|-------------|
| `is_wallet_payment` | Check | Marks payment method as wallet-based |

> **Important**: Payment methods with `is_wallet_payment = 1` are only shown in POS when loyalty is enabled.

### Loyalty Program (ERPNext Standard)

| Field | Description |
|-------|-------------|
| `company` | Company for this program |
| `auto_opt_in` | Auto-enroll customers |
| `conversion_factor` | Points to currency conversion (1 point = X currency) |
| `expense_account` | Account for loyalty expenses |
| `collection_rules` | Rules for earning points |

---

## Doctypes

### Wallet

**Purpose:** Stores wallet information per customer per company

| Field | Type | Description |
|-------|------|-------------|
| `customer` | Link (Customer) | Wallet owner |
| `company` | Link (Company) | Company |
| `account` | Link (Account) | Receivable account |
| `status` | Select | Active / Inactive |
| `current_balance` | Currency | Cached balance |
| `available_balance` | Currency | Balance minus pending |

**Naming:** `{customer}-WALLET`

### Wallet Transaction

**Purpose:** Records all wallet credits and debits

| Field | Type | Description |
|-------|------|-------------|
| `transaction_type` | Select | Credit / Debit / Loyalty Credit |
| `wallet` | Link (Wallet) | Parent wallet |
| `customer` | Link (Customer) | Auto-fetched from wallet |
| `company` | Link (Company) | Auto-fetched from wallet |
| `amount` | Currency | Transaction amount |
| `source_type` | Select | Mode of Payment / Loyalty Program / Manual Adjustment / Refund |
| `source_account` | Link (Account) | Counter account for GL |
| `reference_doctype` | Link (DocType) | Reference document type |
| `reference_name` | Dynamic Link | Reference document |
| `remarks` | Small Text | Transaction notes |

**Naming:** `WT-.YYYY.-`

---

## API Reference

### wallet.py

#### `get_customer_wallet_balance(customer, company, exclude_invoice)`
Returns available wallet balance for customer.

```python
from pos_next.api.wallet import get_customer_wallet_balance

balance = get_customer_wallet_balance(
    customer="CUST-001",
    company="My Company",
    exclude_invoice="SINV-001"  # Optional
)
# Returns: 500.0
```

#### `get_wallet_info(customer, company, pos_profile)`
Returns comprehensive wallet info for POS frontend.

```python
from pos_next.api.wallet import get_wallet_info

info = get_wallet_info(
    customer="CUST-001",
    company="My Company",
    pos_profile="POS Profile"
)
# Returns: {
#     "wallet_enabled": True,
#     "wallet_exists": True,
#     "wallet_balance": 500.0,
#     "wallet_name": "CUST-001-WALLET",
#     "auto_create": True,
#     "loyalty_program": "POS Rewards",
#     "loyalty_to_wallet": True
# }
```

#### `get_or_create_wallet(customer, company, pos_settings)`
Gets existing wallet or creates new one.

```python
from pos_next.api.wallet import get_or_create_wallet

wallet = get_or_create_wallet(
    customer="CUST-001",
    company="My Company"
)
# Returns: Wallet dict or document
```

#### `create_manual_wallet_credit(customer, company, amount, remarks)`
Creates manual wallet credit (admin use).

```python
from pos_next.api.wallet import create_manual_wallet_credit

transaction_name = create_manual_wallet_credit(
    customer="CUST-001",
    company="My Company",
    amount=100,
    remarks="Promotional credit"
)
# Returns: "WT-2024-00001"
```

### wallet_transaction.py

#### `create_wallet_credit(wallet, amount, source_type, ...)`
Creates wallet credit transaction.

```python
from pos_next.pos_next.doctype.wallet_transaction.wallet_transaction import create_wallet_credit

transaction = create_wallet_credit(
    wallet="CUST-001-WALLET",
    amount=100,
    source_type="Manual Adjustment",
    remarks="Promotional credit",
    submit=True
)
```

---

## Hooks & Triggers

### hooks.py

```python
doc_events = {
    "Customer": {
        "after_insert": "pos_next.api.customers.auto_assign_loyalty_program"
    },
    "Sales Invoice": {
        "validate": [
            "pos_next.api.wallet.validate_wallet_payment"
        ],
        "on_submit": [
            "pos_next.api.wallet.process_loyalty_to_wallet"
        ]
    }
}
```

### Hook Functions

| Hook | Trigger | Function | Purpose |
|------|---------|----------|---------|
| Customer.after_insert | New customer created | `auto_assign_loyalty_program` | Assign loyalty program from POS Settings |
| Sales Invoice.validate | Invoice saved | `validate_wallet_payment` | Check wallet balance |
| Sales Invoice.on_submit | Invoice submitted | `process_loyalty_to_wallet` | Convert points to wallet |

---

## Setup Guide

### Prerequisites

1. ERPNext with Loyalty Program module
2. FatehPOS installed
3. Chart of Accounts configured

### Step-by-Step Setup

#### 1. Create Loyalty Program

```
Selling > Loyalty Program > New
├── Program Name: "POS Rewards"
├── Company: [Your Company]
├── Auto Opt In: ✓
├── Conversion Factor: 1.0
├── Expense Account: [Loyalty Expense Account]
└── Collection Rules:
    └── Tier: Base, Min Spent: 0, Factor: 1
```

#### 2. Create Wallet Account

```
Accounting > Chart of Accounts
├── Assets
│   └── Receivables
│       └── Add Child: "Customer Wallet"
│           ├── Account Type: Receivable
│           └── Is Group: No
```

#### 3. Create Wallet Payment Method

```
Accounting > Mode of Payment > New
├── Mode of Payment: "Redeem Points"
├── Type: General
├── Is Wallet Payment: ✓ (REQUIRED!)
└── Accounts:
    └── Company: [Your Company]
        └── Default Account: Customer Wallet
```

#### 4. Add to POS Profile

```
Retail > POS Profile > [Your Profile]
└── Payment Methods:
    └── Add Row: "Redeem Points"
```

#### 5. Configure POS Settings

```
Search: "POS Settings" > New
├── POS Profile: [Your Profile]
├── Enabled: ✓
└── Wallet & Loyalty:
    ├── Enable Loyalty Program: ✓
    ├── Loyalty Program: "POS Rewards" (REQUIRED)
    ├── Wallet Account: "Customer Wallet" (REQUIRED)
    ├── Auto Create Wallet: ✓ (read-only)
    └── Convert to Wallet: ✓ (read-only)
```

---

## GL Entries

### Wallet Credit (Loyalty Conversion)

| Account | Debit | Credit | Party |
|---------|-------|--------|-------|
| Loyalty Expense | 100 | | |
| Customer Wallet (Receivable) | | 100 | Customer |

### Wallet Credit (Manual)

| Account | Debit | Credit | Party |
|---------|-------|--------|-------|
| Expense Account | 100 | | |
| Customer Wallet (Receivable) | | 100 | Customer |

### Wallet Debit (Payment)

| Account | Debit | Credit | Party |
|---------|-------|--------|-------|
| Customer Wallet (Receivable) | 100 | | Customer |
| Revenue/Cash Account | | 100 | |

### Balance Interpretation

```
Wallet Account (Receivable):
- Negative GL Balance = Positive Wallet Credit (we owe customer)
- Positive GL Balance = Customer owes us (no wallet balance)

Wallet Balance = -1 × GL Balance
```

---

## Summary: Configuration Matrix

| Feature | Required Settings |
|---------|-------------------|
| Wallet Payment | `enable_loyalty_program` + Mode of Payment with `is_wallet_payment` |
| Auto-create wallet | `enable_loyalty_program` (always on) |
| Earn points | `enable_loyalty_program` + Loyalty Program |
| Points → Wallet | `enable_loyalty_program` (always on) |
| Auto-assign loyalty | `enable_loyalty_program` + Loyalty Program set |

---

## Quick Reference

### Enable Loyalty & Wallet

```
POS Settings:
├── enable_loyalty_program: ✓
├── Loyalty Program: [Required - Select Program]
├── Wallet Account: [Required - Select Account]
├── auto_create_wallet: ✓ (automatic, read-only)
└── loyalty_to_wallet: ✓ (automatic, read-only)
```

### Disable Loyalty & Wallet

```
POS Settings:
├── enable_loyalty_program: ✗
└── (All other loyalty/wallet fields hidden)
```

### Frontend Behavior

| Loyalty Program | Redeem Points Button |
|-----------------|---------------------|
| Enabled | Visible in Payment Dialog |
| Disabled | **Hidden** from Payment Dialog |
