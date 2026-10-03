import asyncio
import json
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

def test_gflow_requires_installed_mcp_executable(tmp_path):
    p = GFlowProvider(tmp_path)
    p.executable = None
    assert not p.readiness()["ready"]
    frame=tmp_path/"product.jpg"; frame.write_bytes(b"image")
    with pytest.raises(ProviderError, match="ไม่พบ gflow"):
        asyncio.run(p.generate_video("prompt", tmp_path / "clip.mp4", [frame]))

def test_gflow_cli_uses_single_i2v_generation(tmp_path, monkeypatch):
    from app.providers import GFlowProvider
    frame=tmp_path/"product.jpg"; frame.write_bytes(b"image")
    output=tmp_path/"clip.mp4"
    provider=GFlowProvider(tmp_path)
    provider.executable="gflow"
    seen={}
    class Process:
        returncode=0
        async def communicate(self):
            output.write_bytes(b"video")
            return (json.dumps({"status":"ok","local_path":str(output)}).encode(),b"")
    async def run(*args,**kwargs):
        seen.update(args=args,kwargs=kwargs)
        return Process()
    monkeypatch.setattr(asyncio,"create_subprocess_exec",run)
    op=asyncio.run(provider.generate_video("approved prompt",output,[frame],"Cup demo"))
    args=seen["args"]
    assert args[:3]==("gflow","video","i2v")
    assert "--initial-frame" in args and str(frame.resolve()) in args
    assert "approved prompt" in args
    assert args[args.index("--model")+1]=="veo-lite"
    assert "--duration" not in args
    assert args[args.index("--count")+1]=="1"
    assert args[args.index("--project-name")+1]=="Cup demo"
    assert args[args.index("--output")+1]==str(output.resolve())
    assert "--json" in args
    assert op.startswith("gflow-")
    assert asyncio.run(provider.get_operation_status(op))=={"done":True}
    copied=tmp_path/"copied.mp4"
    asyncio.run(provider.download_video(op,copied))
    assert copied.read_bytes()==b"video"

def test_gflow_pre_submit_config_error_is_safe_to_retry(tmp_path, monkeypatch):
    provider=GFlowProvider(tmp_path); provider.executable="gflow"
    frame=tmp_path/"product.jpg"; frame.write_bytes(b"image")
    class Process:
        returncode=1
        async def communicate(self):
            return (json.dumps({"status":"error","error":{"detail":"migrated Flow host renders no duration control offering '8s'"}}).encode(),b"")
    async def run(*args,**kwargs): return Process()
    monkeypatch.setattr(asyncio,"create_subprocess_exec",run)
    with pytest.raises(ProviderError,match="renders no duration control"):
        asyncio.run(provider.generate_video("prompt",tmp_path/"clip.mp4",[frame]))

def test_gflow_cli_uses_r2v_for_multiple_images(tmp_path, monkeypatch):
    provider=GFlowProvider(tmp_path); provider.executable="gflow"
    frames=[]
    for name in ("clean.png","detail.jpg"):
        path=tmp_path/name; path.write_bytes(b"image"); frames.append(path)
    output=tmp_path/"clip.mp4"; seen={}
    class Process:
        returncode=0
        async def communicate(self):
            output.write_bytes(b"video")
            return (json.dumps({"status":"ok","local_path":str(output)}).encode(),b"")
    async def run(*args,**kwargs):
        seen["args"]=args
        return Process()
    monkeypatch.setattr(asyncio,"create_subprocess_exec",run)
    asyncio.run(provider.generate_video("show the product",output,frames))
    args=seen["args"]
    assert args[:3]==("gflow","video","r2v")
    assert [args[i+1] for i,x in enumerate(args) if x=="--ref"]==[str(p.resolve()) for p in frames]
    assert args[args.index("--count")+1]=="1"

def test_gflow_cli_fails_closed_when_output_missing(tmp_path, monkeypatch):
    provider=GFlowProvider(tmp_path); provider.executable="gflow"
    frame=tmp_path/"product.jpg"; frame.write_bytes(b"image")
    class Process:
        returncode=0
        async def communicate(self):
            return (b'{"status":"ok","local_path":"missing.mp4"}',b"")
    async def run(*args,**kwargs): return Process()
    monkeypatch.setattr(asyncio,"create_subprocess_exec",run)
    with pytest.raises(ProviderError,match="without a local video file"):
        asyncio.run(provider.generate_video("prompt",tmp_path/"clip.mp4",[frame]))

