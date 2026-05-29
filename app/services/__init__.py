"""Business-logic layer.

Services own the rules (verification, refund windows, availability accounting)
and raise domain errors from `app.errors`. Routers stay thin — they validate
input, call a service, and commit. Services never import from `app.routers`.
"""
