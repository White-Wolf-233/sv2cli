class SVError(Exception):
    """An actionable command failure."""
    def __init__(self, message, code="invalid_request"):
        super().__init__(message)
        self.code = code
