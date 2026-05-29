"""HTTP routers (FastAPI `APIRouter` instances).

Routers handle request parsing and HTTP semantics only. Business rules live in
`app.services`. Error translation is global (`app.exception_handlers`), so
routers raise domain exceptions directly instead of catching and re-raising.
"""
