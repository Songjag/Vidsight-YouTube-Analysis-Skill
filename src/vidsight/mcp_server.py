"""Official Vidsight MCP API. No network or environment access at import time."""
import json
import logging
import sys
from contextlib import redirect_stdout
from functools import partial
from typing import Literal, Mapping

import anyio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .core.orchestrator import VideoAnalyzer
from .providers.base import ProviderError, VisionResponse
from .providers.transcription.base import TranscriptSegment


class OverviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    url: str = Field(min_length=1, max_length=2048, description="Single YouTube video URL; not a playlist or local file.")


class QuestionInput(OverviewInput):
    question: str = Field(min_length=1, max_length=8000, description="Question grounded in the supplied video evidence.")
    require_vision: bool = Field(default=False, description="Require visual evidence; fail if vision is unavailable.")


class SegmentInput(QuestionInput):
    start: float = Field(ge=0, description="Start time in seconds from the original video.")
    end: float = Field(gt=0, description="End time in seconds; must be greater than start and within the video.")

    @model_validator(mode="after")
    def valid_range(self):
        if self.end <= self.start:
            raise ValueError("end must exceed start")
        return self


class VideoResult(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    video_id: str
    start: float
    end: float
    duration: float
    source: Literal["raw-timeline", "multimodal", "visual-only", "transcript-only", "metadata-only"]
    timeline: list[TranscriptSegment]
    frame_timestamps: list[float]
    submitted_frame_timestamps: list[float] = Field(default_factory=list)
    analysis: VisionResponse | None
    warnings: list[str]


INPUTS = {
    "watch_video_overview": OverviewInput,
    "analyze_video_segment": SegmentInput,
    "ask_video_question": QuestionInput,
}
DESCRIPTIONS = {
    "watch_video_overview": "Summarize a YouTube video with original timestamps. Uses sampled frames/transcript when available; returns raw-timeline without AI if no valid provider is selected.",
    "analyze_video_segment": "Answer a question about a specified video time range. Set require_vision=true for visual claims. Reports missing or reduced evidence; never switches AI providers after errors.",
    "ask_video_question": "Answer a question using evidence across a YouTube video. Set require_vision=true when visual confirmation is required. Sampled evidence does not mean continuous viewing.",
}


def error_result(code: str, message: str) -> CallToolResult:
    return CallToolResult(isError=True, content=[TextContent(
        type="text", text=json.dumps({"error": {"code": code, "message": message}}, ensure_ascii=False))])


class MCPApplication:
    """Bound one analysis at a time; keep worker alive through cleanup on cancellation."""

    def __init__(self, env: Mapping[str, str], *, analyzer: VideoAnalyzer | None = None):
        self.server = Server("vidsight", version="0.1.0",
                             instructions="Use source/warnings/timestamps to qualify conclusions. Raw timeline is not AI analysis.")
        self._limiter = anyio.CapacityLimiter(1)
        self._configuration_error: str | None = None
        try:
            self._analyzer = analyzer if analyzer is not None else VideoAnalyzer(dict(env))
        except ProviderError as exc:
            self._analyzer = None
            self._configuration_error = str(exc)
        self.server.list_tools()(self.list_tools)
        # Validate ourselves so invalid input values never appear in SDK error text.
        self.server.call_tool(validate_input=False)(self.call_tool)

    async def list_tools(self) -> list[Tool]:
        return [Tool(name=name, description=DESCRIPTIONS[name],
                     inputSchema=model.model_json_schema(), outputSchema=VideoResult.model_json_schema(),
                     annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                                 idempotentHint=False, openWorldHint=True))
                for name, model in INPUTS.items()]

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        model = INPUTS.get(name)
        if model is None:
            return error_result("UnknownTool", "Unknown Vidsight tool; use tools/list.")
        try:
            parameters = model.model_validate(arguments)
        except ValidationError:
            return error_result("InvalidArguments", "Arguments do not match the tool input schema; check required fields, types and time range.")
        if self._configuration_error is not None:
            return error_result("ConfigurationError", self._configuration_error)
        try:
            result = await anyio.to_thread.run_sync(
                partial(self._analyzer.analyze, **parameters.model_dump()),
                limiter=self._limiter, abandon_on_cancel=False)
            output = VideoResult.model_validate(result).model_dump(mode="json")
        except ProviderError as exc:
            # ProviderError messages are the pipeline's sanitized public contract.
            return error_result(type(exc).__name__, str(exc))
        except TimeoutError:
            return error_result("ProviderTimeoutError", "Operation timed out; narrow the time range or check endpoint availability.")
        except Exception:
            # Third-party or output validation exceptions can contain media/credentials.
            logging.getLogger(__name__).error("Vidsight tool failed with an unexpected internal error")
            return error_result("InternalError", "Video analysis failed internally; run vidsight doctor and check installation.")
        return CallToolResult(structuredContent=output,
                              content=[TextContent(type="text", text=json.dumps(output, ensure_ascii=False))])


async def serve_stdio(env: Mapping[str, str]) -> None:
    # Capture the protocol stream before redirecting incidental Python prints.
    async with stdio_server() as (read_stream, write_stream):
        with redirect_stdout(sys.stderr):
            application = MCPApplication(env)
            await application.server.run(read_stream, write_stream,
                                          application.server.create_initialization_options())
