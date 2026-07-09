"""
Thin wrapper around the OpenAI SDK pointed at OpenRouter.
Every LLM call in this project (chat generation, test-case generation,
LLM-as-judge) goes through this single client so the API key / base URL
only needs to be configured once.
"""
from openai import OpenAI

from src import config

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.OPENROUTER_API_KEY:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Add it to your .env file "
                "(see .env.example)."
            )
        _client = OpenAI(
            api_key=config.OPENROUTER_API_KEY,
            base_url=config.OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": config.OPENROUTER_SITE_URL,
                "X-Title": config.OPENROUTER_APP_NAME,
            },
        )
    return _client


def chat_completion(
    messages: list[dict],
    model: str = None,
    temperature: float = 0.2,
    max_tokens: int = 800,
    response_format: dict | None = None,
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
) -> tuple[str, list[dict] | None]:
    """Call an OpenRouter chat model and return (text_content, tool_calls).
    
    If the model responds with tool calls, they are returned as a list of dicts
    with keys: name, arguments (JSON string). The caller should execute them
    and call again with the results.
    If no tool calls, returns (text, None).
    """
    from openai.types.chat import ChatCompletionMessageToolCall

    client = get_client()
    kwargs = dict(
        model=model or config.GENERATION_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if response_format:
        kwargs["response_format"] = response_format
    if tools:
        kwargs["tools"] = tools
    if tool_choice:
        kwargs["tool_choice"] = tool_choice

    completion = client.chat.completions.create(**kwargs)
    message = completion.choices[0].message

    # Check for tool calls
    if message.tool_calls:
        tool_calls = []
        for tc in message.tool_calls:
            tool_calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            })
        return message.content or "", tool_calls

    return message.content or "", None


def embed_texts(texts: list[str], model: str = None) -> list[list[float]]:
    """Embed a batch of texts via OpenRouter's OpenAI-compatible endpoint."""
    client = get_client()
    resp = client.embeddings.create(
        model=model or config.EMBEDDING_MODEL,
        input=texts,
    )
    return [d.embedding for d in resp.data]
