"""OpenAI-compatible responses endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic_ai.messages import ModelResponse, ThinkingPart

from agentpool_server.openai_api_server.responses.models import (
    Response,
    ResponseMessage,
    ResponseOutputText,
    ResponseReasoning,
    ResponseToolCall,
    ResponseUsage,
)


if TYPE_CHECKING:
    from agentpool.messaging.messages import ChatMessage
    from agentpool_server.openai_api_server.responses.models import ResponseRequest


async def handle_request(request: ResponseRequest, message: ChatMessage[Any]) -> Response:
    text = ResponseOutputText(text=str(message.content))
    output_msg_id = f"msg_{uuid4().hex}"
    output_msg = ResponseMessage(id=output_msg_id, role="assistant", content=[text])
    output: list[ResponseMessage | ResponseToolCall | ResponseReasoning] = [output_msg]

    reasoning_parts = [
        {"type": "text", "text": p.content}
        for m in message.messages
        if isinstance(m, ModelResponse)
        for p in m.parts
        if isinstance(p, ThinkingPart) and p.content
    ]
    if reasoning_parts:
        output.append(ResponseReasoning(content=reasoning_parts))

    calls = [
        ResponseToolCall(type=f"{tc.tool_name}_call", id=tc.tool_call_id)
        for tc in message.get_tool_calls()
    ]
    output = calls + output

    usage_info: ResponseUsage | None = None
    if message.cost_info and (token_usage := message.cost_info.token_usage):
        # Map the keys correctly from agent's dict to ResponseUsage TypedDict
        input_tk = token_usage.input_tokens
        output_tk = token_usage.output_tokens
        total_tk = token_usage.total_tokens

        usage_info = ResponseUsage(
            input_tokens=input_tk,
            input_tokens_details={},
            output_tokens=output_tk,
            output_tokens_details={},
            total_tokens=total_tk,
        )

    return Response(
        model=request.model,
        output=output,
        instructions=request.instructions,
        max_output_tokens=request.max_output_tokens,
        temperature=request.temperature,
        tools=request.tools,
        tool_choice=request.tool_choice,
        usage=usage_info,
        metadata=request.metadata,
    )
