class ControlError(Exception):
    def __init__(self, code: str, status: int = 409, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.status = status
        self.retryable = retryable
