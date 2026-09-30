import asyncio
import logging
import pytest
from app.providers import poll_operation, TransientError, ProviderError, redact, SecretFilter, GFlowProvider

class Fake:
    def __init__(self, errors=0, done=True):
        self.errors, self.done, self.calls = errors, done, 0
    async def get_operation_status(self, operation):
        self.calls += 1
        if self.calls <= self.errors:
            raise TransientError("temporary")
        return {"done": self.done}

def test_retry_transient_status_only():
    p = Fake(errors=2)
    assert asyncio.run(poll_operation(p,"op",timeout=1,max_retries=2,initial_delay=.001))["done"]
    assert p.calls == 3

def test_auth_error_is_not_retried():
    class Auth(Fake):
        async def get_operation_status(self, operation):
            self.calls += 1
            raise ProviderError("permission denied")
    p = Auth()
    with pytest.raises(ProviderError):
        asyncio.run(poll_operation(p,"op",timeout=1,max_retries=2,initial_delay=.001))
    assert p.calls == 1

def test_timeout():
    with pytest.raises(TimeoutError):
        asyncio.run(poll_operation(Fake(done=False),"op",timeout=.01,max_retries=2,initial_delay=.002))

def test_secret_redaction(caplog):
    secret = "AIza" + "X"*35
    logger = logging.getLogger("test-secret")
    f = SecretFilter([secret])
    logger.addFilter(f)
    try:
        with caplog.at_level(logging.ERROR):
            logger.error("api_key=%s Authorization: Bearer top-secret", secret)
        assert secret not in caplog.text
        assert "top-secret" not in caplog.text
        assert "REDACTED" in caplog.text
    finally:
        logger.removeFilter(f)

def test_gflow_does_not_generate_without_verified_readiness(tmp_path):
    p = GFlowProvider(tmp_path)
    with pytest.raises(ProviderError, match="blocked"):
        asyncio.run(p.generate_video("prompt", tmp_path / "clip.mp4"))

