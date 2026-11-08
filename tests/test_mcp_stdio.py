"""Real subprocess stdio handshake, no external media/provider calls."""
import json
import os
import sys
from datetime import timedelta

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_cli_stdio(tmp_path):
    env_file = tmp_path / "test.env"
    env_file.write_text("LLM_PROVIDER=none\nSTT_PROVIDER=none\n")
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME"}}
    env.update(LLM_PROVIDER="none", STT_PROVIDER="none")
    parameters = StdioServerParameters(command=sys.executable,
        args=["-m", "vidsight", "--env-file", str(env_file), "serve"], env=env)
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=15)) as client:
            initialized = await client.initialize()
            assert initialized.serverInfo.name == "vidsight"
            tools = await client.list_tools()
            assert len(tools.tools) == 3
            result = await client.call_tool("watch_video_overview", {"url": "file:///not-youtube"})
            assert result.isError
            assert json.loads(result.content[0].text)["error"]["code"] == "ConfigurationError"
            await client.send_ping()


@pytest.mark.asyncio
async def test_stdio_success_and_stdout_isolation(tmp_path):
    # Test-only bootstrap; production does not expose a mock mode.
    bootstrap = '''
import anyio
from vidsight import mcp_server
class FakeAnalyzer:
    def __init__(self, env):
        pass
    def analyze(self, **kwargs):
        print("worker diagnostic")
        return {"video_id": "abcdefghijk", "start": 0, "end": 1, "duration": 1,
                "source": "raw-timeline", "timeline": [], "frame_timestamps": [],
                "analysis": None, "warnings": ["mock"]}
mcp_server.VideoAnalyzer = FakeAnalyzer
anyio.run(mcp_server.serve_stdio, {})
'''
    parameters = StdioServerParameters(command=sys.executable, args=["-c", bootstrap])
    logfile = tmp_path / "stderr.log"
    with logfile.open("w") as log:
        async with stdio_client(parameters, errlog=log) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=15)) as client:
                await client.initialize()
                result = await client.call_tool("watch_video_overview", {"url": "https://youtu.be/abcdefghijk"})
                assert not result.isError and result.structuredContent["source"] == "raw-timeline"
                await client.send_ping()
    assert "worker diagnostic" in logfile.read_text()
