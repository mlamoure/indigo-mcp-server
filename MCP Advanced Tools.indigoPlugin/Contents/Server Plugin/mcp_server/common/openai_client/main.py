import functools
import logging
import os
import re
from typing import Any, Dict, Optional, Sequence, Type, Union

import tiktoken
from langsmith.wrappers import wrap_openai
from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger("Plugin")

DEFAULT_SYSTEM_PROMPT = (
    "You are an automation assistant supporting a home automation system called Indigo."
)
# Defaults used when the plugin has not exported a model choice. The plugin
# sets SMALL_MODEL / OPENAI_EMBEDDING_MODEL in os.environ from its prefs; they
# are read at call time (never cached at import) because this module is
# imported before the plugin's startup() applies its configuration.
DEFAULT_SMALL_MODEL = "gpt-6-luna"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"

# text-embedding-3-large is 3072-dimensional natively; requesting 1536 keeps
# the index width (and storage) of the old text-embedding-3-small tables.
EMBEDDING_DIMENSIONS = 1536

# Total context per model. A guard against runaway prompts only (every prompt
# this plugin builds is a few thousand tokens), so unknown models fall back
# to a conservative bound instead of raising KeyError.
MODEL_TOKEN_LIMITS = {
    "gpt-6-luna": 400000,
    "gpt-5.4": 1000000,
    "gpt-5.4-mini": 400000,
    "gpt-5.4-nano": 400000,
    "gpt-5-mini": 400000,
}
DEFAULT_TOKEN_LIMIT = 128000
DEFAULT_RESPONSE_TOKEN_RESERVE = int(
    os.environ.get("OPENAI_RESPONSE_TOKEN_RESERVE", 2000)
)


def get_small_model() -> str:
    """The small model for keyword generation, query expansion and property picking."""
    return os.environ.get("SMALL_MODEL") or DEFAULT_SMALL_MODEL


def get_embedding_model() -> str:
    """The embedding model for the search index and query vectors."""
    return os.environ.get("OPENAI_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL


def embedding_request_params() -> Dict[str, Any]:
    """Model (and fixed output width) for every embeddings.create call."""
    model = get_embedding_model()
    params: Dict[str, Any] = {"model": model}
    # Only the text-embedding-3 family accepts `dimensions`
    if model.startswith("text-embedding-3"):
        params["dimensions"] = EMBEDDING_DIMENSIONS
    return params


def low_reasoning_effort(model: str) -> Optional[str]:
    """
    The lowest reasoning effort a model accepts, for short utility calls
    (keyword generation, query expansion, property picking) where thinking
    only adds latency.

    gpt-5.1+ and gpt-6 accept "none" (except the gpt-6 Sol and Astra tiers,
    whose lowest is "low"); the original gpt-5 family's lowest is "minimal";
    o-series models start at "low". Non-reasoning models take no effort.
    """
    m = (model or "").lower()
    if m.startswith("gpt-6"):
        return "low" if ("sol" in m or "astra" in m) else "none"
    if re.match(r"gpt-5\.\d", m):
        return "none"
    if m.startswith("gpt-5"):
        return "minimal"
    if re.match(r"o\d", m):
        return "low"
    return None


def _token_limit(model: str) -> int:
    return MODEL_TOKEN_LIMITS.get(model, DEFAULT_TOKEN_LIMIT)


# Lazy-initialize the OpenAI client
_client = None
_embedding_client = None

# Cache for token encoders
_token_encoders = {}


@functools.lru_cache(maxsize=128)
def _get_token_encoder(model: str):
    """Get cached token encoder for a model."""
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        # tiktoken has no mapping for gpt-6 yet; it uses o200k_base like gpt-5
        if model.startswith(("gpt-6", "gpt-5", "o")):
            return tiktoken.get_encoding("o200k_base")
        return tiktoken.get_encoding("cl100k_base")


def _count_message_tokens(
    msgs: Union[Sequence[dict], Dict[str, Any]], model: str
) -> int:
    enc = _get_token_encoder(model)
    total = 0
    for m in msgs:
        # support both dicts and chat-message objects
        content = m["content"] if isinstance(m, dict) else getattr(m, "content", "")
        total += len(enc.encode(content))
    return total


def _get_client():
    global _client
    if _client is None:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY must be set before calling OpenAI endpoints"
            )
        raw = OpenAI(api_key=key)
        # Wrap with LangSmith for tracing, but don't create duplicate traces
        # The trace context is already established by the parent
        _client = wrap_openai(raw)
        logger.debug("🤖 OpenAI client initialized with LangSmith wrapper")
    return _client


def _get_embedding_client():
    """Get OpenAI client for embeddings without LangSmith tracing."""
    global _embedding_client
    if _embedding_client is None:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY must be set before calling OpenAI endpoints"
            )
        # Use raw OpenAI client without LangSmith wrapper for embeddings
        # to avoid tracing overhead and noise in LangSmith traces
        _embedding_client = OpenAI(api_key=key)
        logger.debug("🔧 OpenAI embedding client initialized (no LangSmith tracing)")
    return _embedding_client


def emb_texts_batch(texts: list, entity_names: list = None, progress_callback: callable = None) -> list:
    """Get embeddings for multiple texts using OpenAI's embedding model with optimized batching."""
    # Check if parallel processing should be used
    from .parallel_embeddings import should_use_parallel_processing, get_optimal_concurrency, emb_texts_batch_parallel
    
    if should_use_parallel_processing(len(texts)):
        max_concurrent = get_optimal_concurrency(len(texts))
        # Use parallel embedding processing
        
        # Try parallel processing first
        result = emb_texts_batch_parallel(texts, entity_names, progress_callback, max_concurrent)
        
        # Check if parallel processing was successful (not all empty embeddings)
        successful_embeddings = sum(1 for emb in result if emb)
        success_rate = successful_embeddings / len(texts) if texts else 0
        
        if success_rate >= 0.5:  # At least 50% success
            # Parallel processing succeeded
            return result
        else:
            logger.warning(f"⚠️ Parallel embedding processing had low success rate ({success_rate:.1%}), falling back to sequential processing")
    else:
        # Use sequential embedding processing
        pass
    # Fallback to sequential processing
    return _emb_texts_batch_sequential(texts, entity_names, progress_callback)


def _emb_texts_batch_sequential(texts: list, entity_names: list = None, progress_callback: callable = None) -> list:
    """Get embeddings using sequential batch processing (original implementation)."""
    import time
    
    if not texts or len(texts) == 0:
        logger.warning("⚠️ Empty text list provided for batch embedding, returning empty list")
        return []

    # Filter out empty texts and keep track of original indices
    valid_texts = []
    valid_indices = []
    for i, text in enumerate(texts):
        if text and text.strip():
            valid_texts.append(text.strip())
            valid_indices.append(i)
    
    if not valid_texts:
        logger.warning("⚠️ No valid texts provided for batch embedding, returning empty list")
        return [[] for _ in texts]  # Return empty embeddings for all inputs

    max_retries = 3
    base_delay = 1.0
    batch_size = min(len(valid_texts), 100)  # OpenAI allows up to 2048, but we'll be conservative

    embeddings_result = [[] for _ in texts]  # Initialize with empty embeddings

    for attempt in range(max_retries):
        try:
            client = _get_embedding_client()  # Use embedding client without LangSmith
            embedding_params = embedding_request_params()

            # Calculate total batches for progress tracking
            total_batches = (len(valid_texts) + batch_size - 1) // batch_size
            processed_count = 0
            
            # Report start of embedding processing
            if progress_callback:
                # Start embedding batch processing
                pass
            # Process in batches
            for batch_num, i in enumerate(range(0, len(valid_texts), batch_size), 1):
                batch_start_time = time.time()
                batch_texts = valid_texts[i:i + batch_size]
                batch_indices = valid_indices[i:i + batch_size]
                
                # Get entity names for this batch if provided
                batch_entity_names = []
                if entity_names:
                    for idx in batch_indices:
                        if idx < len(entity_names) and entity_names[idx]:
                            batch_entity_names.append(entity_names[idx])
                
                # Debug log before API call
                if batch_entity_names:
                    entity_list = ", ".join(batch_entity_names[:5])  # Show first 5 names
                    if len(batch_entity_names) > 5:
                        entity_list += f" (+{len(batch_entity_names) - 5} more)"
                    # Process batch
                else:
                    # Process batch
                    pass
                # Add timeout to prevent hanging
                response = client.embeddings.create(
                    **embedding_params,
                    input=batch_texts,
                    timeout=60.0  # Longer timeout for batch processing
                )

                # Validate response structure
                if not response or not response.data or len(response.data) != len(batch_texts):
                    raise ValueError(f"Invalid or incomplete response from OpenAI embeddings API: expected {len(batch_texts)} embeddings, got {len(response.data) if response.data else 0}")

                # Map embeddings back to original indices
                for j, embedding_data in enumerate(response.data):
                    original_index = batch_indices[j]
                    embedding = embedding_data.embedding
                    if not embedding or len(embedding) == 0:
                        logger.warning(f"Empty embedding returned for text at index {original_index}")
                        embeddings_result[original_index] = []
                    else:
                        embeddings_result[original_index] = embedding
                
                processed_count += len(batch_texts)
                time.time() - batch_start_time
                
                # Debug log after successful API call
                # Batch completed
                
                # Report progress after each batch
                if progress_callback:
                    progress_callback(batch_num, total_batches, batch_size)

            logger.debug(f"✅ Generated {len([e for e in embeddings_result if e])} batch embeddings from {len(texts)} inputs")
            return embeddings_result

        except Exception as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"⚠️ Batch embedding attempt {attempt + 1}/{max_retries} failed: {e}, retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                logger.error(f"❌ All {max_retries} batch embedding attempts failed: {e}")
                return [[] for _ in texts]  # Return empty embeddings for all inputs

    return [[] for _ in texts]


def emb_text(text: str) -> list:
    """Get embeddings for text using OpenAI's embedding model."""
    import time

    if not text or not text.strip():
        logger.warning("⚠️ Empty text provided for embedding, returning empty list")
        return []

    max_retries = 3
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            client = _get_embedding_client()  # Use embedding client without LangSmith

            # Add timeout to prevent hanging
            response = client.embeddings.create(
                **embedding_request_params(), input=text, timeout=30.0  # 30 second timeout
            )

            # Validate response structure
            if not response or not response.data or len(response.data) == 0:
                raise ValueError("Invalid or empty response from OpenAI embeddings API")

            embedding = response.data[0].embedding
            if not embedding or len(embedding) == 0:
                raise ValueError("Empty embedding returned from OpenAI API")

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Generated embedding ({len(embedding)} dimensions)")
            return embedding

        except Exception as e:
            error_msg = f"Attempt {attempt + 1}/{max_retries} failed for embedding generation: {e}"

            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt)  # Exponential backoff
                logger.warning(f"⚠️ {error_msg}, retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                logger.error(f"❌ {error_msg}, all retries exhausted")
                # Return empty list as fallback instead of crashing
                return []


def _create_with_effort(create, kwargs: Dict[str, Any]):
    """
    Call a chat-completions method, retrying once without reasoning_effort
    when the model rejects the value (each model family accepts a different
    set, and a stale or unknown model choice must not break the call).
    """
    try:
        return create(**kwargs)
    except Exception as e:
        if "reasoning_effort" in kwargs and "reasoning_effort" in str(e):
            logger.debug(
                f"{kwargs.get('model')} rejected reasoning_effort="
                f"{kwargs['reasoning_effort']!r}; retrying without it"
            )
            retry = dict(kwargs)
            retry.pop("reasoning_effort")
            return create(**retry)
        raise


def perform_completion(
    messages: Union[str, Sequence[Any]],
    model: str,
    response_model: Optional[Type[BaseModel]] = None,
    tools: Optional[Union[Dict[str, Any], Sequence[Any]]] = None,
    response_token_reserve: Optional[int] = None,
    reasoning_effort: Optional[str] = None,
) -> Union[str, BaseModel, Dict[str, Any]]:
    """
    Perform a chat completion.

    - With tools, returns {"content": ..., "tool_calls": [...]}.
    - With a response_model, returns the parsed model (or the raw content
      string when parsing is unavailable).
    - Otherwise returns the message content ("" on failure).

    Args:
        messages: A user prompt string, or a list of chat messages
        model: The model to use (required: every caller names its model)
        response_model: Optional Pydantic model for structured output
        tools: Optional tools/functions to make available
        response_token_reserve: Token reserve for the response
        reasoning_effort: Optional reasoning effort; dropped automatically
            if the model rejects it
    """
    if not model:
        raise ValueError("perform_completion requires a model")

    # reserve tokens for the model's response
    response_token_reserve = response_token_reserve or DEFAULT_RESPONSE_TOKEN_RESERVE

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"OpenAI completion: {model} (effort: {reasoning_effort or 'default'})")

    # normalize into `msgs`
    if isinstance(messages, str):
        msgs = [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": messages},
        ]
    else:
        msgs = messages
        if not isinstance(msgs, (list, tuple)):
            msgs = [msgs]

    # normalize any message objects into simple dicts
    normalized_msgs = []
    for m in msgs:
        if isinstance(m, dict):
            normalized_msgs.append(m)
        else:
            role = getattr(m, "role", None)
            if not role:
                typ = getattr(m, "type", None)
                if typ == "human":
                    role = "user"
                elif typ in ("ai", "assistant"):
                    role = "assistant"
                elif typ in ("system", "developer"):
                    role = typ
                else:
                    role = "user"
            content = getattr(m, "content", "")
            normalized_msgs.append({"role": role, "content": content})
    msgs = normalized_msgs

    # enforce token limit
    token_limit = _token_limit(model)
    total_tokens = _count_message_tokens(msgs, model)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Tokens: {total_tokens:,} (limit: {token_limit:,})")

    if total_tokens + response_token_reserve > token_limit:
        raise RuntimeError(
            f"Prompt too large: needs {total_tokens + response_token_reserve:,} tokens (limit {token_limit:,})."
        )

    client = _get_client()
    if client is None:
        logger.error("❌ Failed to initialize OpenAI client")
        return ""

    base_params: Dict[str, Any] = {"model": model, "messages": msgs}
    if reasoning_effort:
        base_params["reasoning_effort"] = reasoning_effort

    # If tools provided, call OpenAI Chat Completions endpoint
    if tools is not None:
        tools_list = list(tools.values()) if isinstance(tools, dict) else tools
        params = dict(base_params, tools=tools_list, tool_choice="auto")
        chat_resp = _create_with_effort(client.chat.completions.create, params)
        if chat_resp is None:
            return ""

        if chat_resp.choices and chat_resp.choices[0].message:
            message = chat_resp.choices[0].message
            result = {"content": message.content, "tool_calls": []}

            # Handle function_call (older format)
            if hasattr(message, "function_call") and message.function_call:
                result["tool_calls"] = [
                    {
                        "function": {
                            "name": message.function_call.name,
                            "arguments": message.function_call.arguments,
                        }
                    }
                ]

            # Handle tool_calls (newer format)
            if hasattr(message, "tool_calls") and message.tool_calls:
                result["tool_calls"] = [
                    {
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in message.tool_calls
                ]

            logger.debug(
                f"🔧 Received response with {len(result['tool_calls'])} tool calls"
            )
            return result

        return ""

    chat_resp = None
    if response_model:
        # Structured output via chat.completions.parse()
        logger.debug(f"🔧 Using structured output with {response_model.__name__}")
        try:
            chat_resp = _create_with_effort(
                client.chat.completions.parse,
                dict(base_params, response_format=response_model),
            )

            if hasattr(chat_resp, 'choices') and chat_resp.choices:
                choice = chat_resp.choices[0]
                if hasattr(choice, 'message') and hasattr(choice.message, 'parsed'):
                    parsed_obj = choice.message.parsed
                    if parsed_obj:
                        return parsed_obj
                    else:
                        logger.warning("⚠️ Parsed object is None, trying content fallback")

                # Fallback to content if parsed is not available
                if hasattr(choice.message, 'content') and choice.message.content:
                    return choice.message.content

        except Exception as e:
            logger.warning(f"⚠️ Structured output parse failed, falling back to regular completion: {e}")

            # Fallback to regular completion if structured output fails
            try:
                chat_resp = _create_with_effort(client.chat.completions.create, base_params)
                if chat_resp and chat_resp.choices and chat_resp.choices[0].message:
                    content = chat_resp.choices[0].message.content
                    if content:
                        return content
            except Exception as fallback_error:
                logger.error(f"❌ Fallback completion also failed: {fallback_error}")
                return ""
    else:
        # Standard chat completion
        try:
            chat_resp = _create_with_effort(client.chat.completions.create, base_params)
        except Exception as e:
            logger.error(f"❌ Standard completion failed: {e}")
            return ""

    # Extract content from OpenAI response
    if chat_resp and chat_resp.choices and chat_resp.choices[0].message:
        content = chat_resp.choices[0].message.content
        return content or ""

    logger.warning("⚠️ Empty or invalid response from OpenAI Chat Completions API")
    return ""
