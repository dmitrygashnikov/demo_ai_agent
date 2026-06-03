"""Application authentication package (JWT + password hashing).

This is the APPLICATION's own auth layer — completely independent of Langfuse
(which has its own separate admin account). Provides password hashing, JWT
issuing/verification and FastAPI dependencies for protecting endpoints.
"""
