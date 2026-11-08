import json
import threading
from pathlib import Path

import anyio
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from vidsight.core import orchestrator
from vidsight.mcp_server import MCPApplication
from vidsight.providers.base import ProviderResponseError, ProviderTimeoutError, VisionResponse
from vidsight.providers.transcription.base import TranscriptSegment

URL = "https://youtu.be/abcdefghijk"
RAW = {"video_id": "abcdefghijk", "start": 0, "end": 10, "duration": 10,
       "source": "raw-timeline", "timeline": [], "frame_timestamps": [],
       "analysis": None, "warnings": ["No AI provider"]}


class FakeAnalyzer:
    def __init__(self):
        self.calls = []

    def analyze(self, **kwargs):
        self.calls.append(kwargs)
        return RAW


def error_code(result):
    assert result.isError
    assert result.structuredContent is None
    return json.loads(result.content[0].text)["error"]["code"]


@pytest.mark.asyncio
async def test_schema_and_routing():
    fake = FakeAnalyzer()
    app = MCPApplication({}, analyzer=fake)
    tools = {tool.name: tool for tool in await app.list_tools()}
    assert set(tools) == {"watch_video_overview", "analyze_video_segment", "ask_video_question"}
    expected = {"watch_video_overview": {"url"}, "analyze_video_segment": {"url", "start", "end", "question"},
                "ask_video_question": {"url", "question"}}
    for name, tool in tools.items():
        assert set(tool.inputSchema["required"]) == expected[name]
        assert tool.inputSchema["additionalProperties"] is False
        assert tool.description and tool.outputSchema["properties"]["analysis"]
    assert tools["ask_video_question"].inputSchema["properties"]["require_vision"]["default"] is False
    calls = [("watch_video_overview", {"url": URL}),
             ("analyze_video_segment", {"url": URL, "start": 1, "end": 4, "question": "What?", "require_vision": True}),
             ("ask_video_question", {"url": URL, "question": "Why?"})]
    for name, args in calls:
        result = await app.call_tool(name, args)
        assert not result.isError
        assert json.loads(result.content[0].text) == result.structuredContent
        assert result.structuredContent["submitted_frame_timestamps"] == []
    assert fake.calls == [calls[0][1], calls[1][1], {**calls[2][1], "require_vision": False}]


@pytest.mark.asyncio
@pytest.mark.parametrize("name,args", [
    ("watch_video_overview", {}),
    ("watch_video_overview", {"url": 1}),
    ("watch_video_overview", {"url": URL, "extra": "private-secret"}),
    ("ask_video_question", {"url": URL, "question": ""}),
    ("ask_video_question", {"url": URL, "question": "q", "require_vision": "false"}),
    ("analyze_video_segment", {"url": URL, "start": 5, "end": 1, "question": "q"}),
    ("analyze_video_segment", {"url": URL, "start": -1, "end": 1, "question": "q"}),
    ("analyze_video_segment", {"url": URL, "start": float("nan"), "end": 1, "question": "q"}),
])
async def test_input_validation_does_not_run_pipeline(name, args):
    fake = FakeAnalyzer()
    result = await MCPApplication({}, analyzer=fake).call_tool(name, args)
    assert error_code(result) == "InvalidArguments"
    assert "private-secret" not in result.content[0].text
    assert not fake.calls


@pytest.mark.asyncio
async def test_invalid_url_missing_key_and_vision():
    result = await MCPApplication({}).call_tool("watch_video_overview", {"url": "file:///private-secret"})
    assert error_code(result) == "ConfigurationError"
    assert "private-secret" not in result.content[0].text
    app = MCPApplication({"LLM_PROVIDER": "openai", "LLM_MODEL": "m"})
    assert len(await app.list_tools()) == 3
    assert error_code(await app.call_tool("watch_video_overview", {"url": URL})) == "ConfigurationError"
    app = MCPApplication({"LLM_PROVIDER": "ollama", "LLM_MODEL": "m"})
    assert error_code(await app.call_tool("ask_video_question", {
        "url": URL, "question": "What is visible?", "require_vision": True})) == "UnsupportedCapabilityError"


@pytest.mark.asyncio
@pytest.mark.parametrize("exc,code", [
    (ProviderResponseError("YouTube download failed"), "ProviderResponseError"),
    (ProviderTimeoutError("Provider timed out"), "ProviderTimeoutError"),
    (TimeoutError("private-secret"), "ProviderTimeoutError"),
    (RuntimeError("private-secret"), "InternalError"),
])
async def test_errors(exc, code, caplog):
    class Broken:
        def analyze(self, **kwargs):
            raise exc
    result = await MCPApplication({}, analyzer=Broken()).call_tool("watch_video_overview", {"url": URL})
    assert error_code(result) == code
    assert "private-secret" not in result.content[0].text + caplog.text


@pytest.mark.asyncio
async def test_invalid_output_is_sanitized(caplog):
    class Broken:
        def analyze(self, **kwargs):
            return {"private-secret": "sensitive transcript"}
    result = await MCPApplication({}, analyzer=Broken()).call_tool("watch_video_overview", {"url": URL})
    assert error_code(result) == "InternalError"
    assert "private-secret" not in result.content[0].text + caplog.text
    assert "sensitive transcript" not in result.content[0].text + caplog.text


@pytest.mark.asyncio
async def test_protocol_error_keeps_connection_alive():
    app = MCPApplication({"LLM_PROVIDER": "openai", "LLM_MODEL": "m"})
    async with create_connected_server_and_client_session(app.server) as client:
        result = await client.call_tool("watch_video_overview", {"url": URL})
        assert error_code(result) == "ConfigurationError"
        assert len((await client.list_tools()).tools) == 3
        await client.send_ping()


@pytest.mark.asyncio
async def test_initialize_list_call_real_pipeline_mock_media(monkeypatch):
    monkeypatch.setattr(orchestrator, "fetch_subtitles", lambda _: [TranscriptSegment(1, 2, "hello")])
    directories = []
    def download(url, directory):
        directories.append(directory)
        return Path(directory) / "video.mp4", 10
    monkeypatch.setattr(orchestrator.youtube, "download", download)
    class Provider:
        closed = False
        def generate(self, req):
            assert "hello" in req.blocks[0].text
            return VisionResponse("summary", "ollama", "test-model")
        def close(self):
            self.closed = True
    provider = Provider()
    monkeypatch.setattr(orchestrator, "create_provider", lambda _: provider)
    for env, source in [({}, "raw-timeline"), ({"LLM_PROVIDER": "ollama", "LLM_MODEL": "test-model"}, "transcript-only")]:
        app = MCPApplication(env)
        async with create_connected_server_and_client_session(app.server) as client:
            listed = await client.list_tools()
            assert len(listed.tools) == 3
            for name, args in [("watch_video_overview", {"url": URL}),
                               ("ask_video_question", {"url": URL, "question": "q"}),
                               ("analyze_video_segment", {"url": URL, "start": 0, "end": 3, "question": "q"})]:
                result = await client.call_tool(name, args)
                assert not result.isError
                assert result.structuredContent["source"] == source
                assert result.structuredContent["timeline"][0]["start"] == 1
            invalid = await client.call_tool("watch_video_overview", {"url": URL, "unexpected": "secret"})
            assert error_code(invalid) == "InvalidArguments"
    assert provider.closed
    assert all(not directory.exists() for directory in directories)


@pytest.mark.asyncio
async def test_worker_does_not_block_loop_and_serializes_calls():
    entered, release = threading.Event(), threading.Event()
    calls = []
    class Blocking:
        def analyze(self, **kwargs):
            calls.append(threading.get_ident())
            entered.set()
            assert release.wait(3)
            return RAW
    app = MCPApplication({}, analyzer=Blocking())
    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            group.start_soon(app.call_tool, "watch_video_overview", {"url": URL})
            while not entered.is_set():
                await anyio.sleep(.01)
            group.start_soon(app.call_tool, "watch_video_overview", {"url": URL})
            await anyio.sleep(.03)
            assert len(calls) == 1 and calls[0] != threading.get_ident()
            release.set()
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_cancellation_waits_for_cleanup():
    entered, release, cleaned = threading.Event(), threading.Event(), threading.Event()
    class Blocking:
        def analyze(self, **kwargs):
            try:
                entered.set()
                assert release.wait(3)
                return RAW
            finally:
                cleaned.set()
    app = MCPApplication({}, analyzer=Blocking())
    scope = anyio.CancelScope()
    async def run():
        with scope:
            await app.call_tool("watch_video_overview", {"url": URL})
        assert cleaned.is_set()
    with anyio.fail_after(5):
        async with anyio.create_task_group() as group:
            group.start_soon(run)
            while not entered.is_set():
                await anyio.sleep(.01)
            scope.cancel()
            await anyio.sleep(.01)
            assert not cleaned.is_set()
            release.set()
