"""Payment providers: one class per way to pay (Stripe, manual, ...).

base.py      PaymentProvider — what every provider must implement
manual.py    ManualProvider — payments entered by a manager
registry.py  "stripe" / "manual" -> provider object
"""
