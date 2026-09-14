"""Shared API error type: carries an HTTP status for REST and a message
that both REST and MCP surfaces can show to the caller."""


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
