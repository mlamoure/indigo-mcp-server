import functools
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Type, Union, Iterable

import tiktoken
from jinja2 import Environment, FileSystemLoader
from langsmith.wrappers import wrap_openai
from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger("Plugin")

DEFAULT_SYSTEM_PROMPT = (
    "You are an automation assistant supporting a home automation system called Indigo."
)
DEFAULT_MODEL = os.environ.get("LARGE_MODEL", "gpt-5")
SMALL_MODEL = os.environ.get("SMALL_MODEL", "gpt-5-mini")

# hard-coded model limits and defaults
MODEL_TOKEN_LIMITS = {
    "gpt-4o": 128000,
    "gpt-4.1": 1047576,
    "o4-mini": 200000,
    "gpt-4o-mini": 1047576,
    "gpt-5": 1047576,
    "gpt-5-mini": 400000,
}
DEFAULT_RESPONSE_TOKEN_RESERVE = int(
    os.environ.get("OPENAI_RESPONSE_TOKEN_RESERVE", 2000)
)
DEFAULT_MAX_ITEMS_PER_CHUNK = int(os.environ.get("OPENAI_MAX_ITEMS_PER_CHUNK", 100))
DEFAULT_SUMMARIZATION_MODEL = os.environ.get(
    "OPENAI_SUMMARIZATION_MODEL", DEFAULT_MODEL
)

# initialize summarization template environment
_template_dir = Path(__file__).parent.parent.parent / "prompts"
_env = Environment(
    loader=FileSystemLoader(str(_template_dir), encoding="utf-8"), autoescape=False
)

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


def select_optimal_model(
    messages: Union[str, Sequence[Any], Dict[str, Any]],
    default_model: Optional[str] = None,
    small_model: Optional[str] = None,
) -> str:
    """
    Select optimal model based on token count.

    Automatically selects between small and large models based on their token limits.
    Raises an error if the token count exceeds the large model's limit.

    Args:
        messages: The messages to analyze
        default_model: Large model to use for complex tasks
        small_model: Small model to use for simple tasks

    Returns:
        The optimal model name to use

    Raises:
        RuntimeError: If token count exceeds the large model's limit
    """
    default_model = default_model or DEFAULT_MODEL
    small_model = small_model or SMALL_MODEL

    # Count tokens in all messages
    enc = _get_token_encoder(small_model)
    token_count = 0

    if isinstance(messages, str):
        token_count = len(enc.encode(messages))
    elif isinstance(messages, dict):
        # Sum tokens from all values in the dict
        for value in messages.values():
            token_count += len(enc.encode(str(value)))
    elif isinstance(messages, (list, tuple)):
        # Sum tokens from all messages in the list
        for msg in messages:
            if isinstance(msg, dict):
                # Sum tokens from all content in the message dict
                for value in msg.values():
                    token_count += len(enc.encode(str(value)))
            else:
                # Handle message objects or strings
                content = getattr(msg, "content", str(msg))
                token_count += len(enc.encode(str(content)))
    else:
        # Handle single message object
        content = getattr(messages, "content", str(messages))
        token_count += len(enc.encode(str(content)))

    # Get token limits for models
    small_model_limit = MODEL_TOKEN_LIMITS.get(small_model, 200000)
    large_model_limit = MODEL_TOKEN_LIMITS.get(default_model, 1047576)

    # Check if token count exceeds large model limit
    if token_count > large_model_limit:
        raise RuntimeError(
            f"Token count ({token_count:,}) exceeds large model limit ({large_model_limit:,}) for {default_model}"
        )

    # Select model based on token count vs small model limit
    selected_model = small_model if token_count < small_model_limit else default_model

    logger.debug(
        f"🧠 Model selection: {token_count:,} tokens → {selected_model} "
        f"(small limit: {small_model_limit:,}, large limit: {large_model_limit:,})"
    )

    return selected_model


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
        logger.debug(f"🚀 Using parallel embedding processing with {max_concurrent} concurrent batches for {len(texts)} texts")
        
        # Try parallel processing first
        result = emb_texts_batch_parallel(texts, entity_names, progress_callback, max_concurrent)
        
        # Check if parallel processing was successful (not all empty embeddings)
        successful_embeddings = sum(1 for emb in result if emb)
        success_rate = successful_embeddings / len(texts) if texts else 0
        
        if success_rate >= 0.5:  # At least 50% success
            logger.debug(f"✅ Parallel embedding processing succeeded with {successful_embeddings}/{len(texts)} embeddings ({success_rate:.1%} success rate)")
            return result
        else:
            logger.warning(f"⚠️ Parallel embedding processing had low success rate ({success_rate:.1%}), falling back to sequential processing")
    else:
        logger.debug(f"📊 Using sequential embedding processing for {len(texts)} texts (below parallel threshold)")
    
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
            model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

            # Calculate total batches for progress tracking
            total_batches = (len(valid_texts) + batch_size - 1) // batch_size
            processed_count = 0
            
            # Report start of embedding processing
            if progress_callback:
                logger.debug(f"📊 Starting embedding batch processing: {total_batches} batches of max {batch_size} texts each")
            
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
                    logger.debug(f"🔄 Processing batch {batch_num}/{total_batches} ({len(batch_texts)} embeddings): [{entity_list}]")
                else:
                    logger.debug(f"🔄 Processing batch {batch_num}/{total_batches} ({len(batch_texts)} embeddings)")
                
                # Add timeout to prevent hanging
                response = client.embeddings.create(
                    model=model, 
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
                batch_time = time.time() - batch_start_time
                
                # Debug log after successful API call
                logger.debug(f"✅ Batch {batch_num}/{total_batches} completed in {batch_time:.2f}s ({len(batch_texts)} embeddings processed, {processed_count}/{len(valid_texts)} total)")
                
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
            model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

            # Add timeout to prevent hanging
            response = client.embeddings.create(
                model=model, input=text, timeout=30.0  # 30 second timeout
            )

            # Validate response structure
            if not response or not response.data or len(response.data) == 0:
                raise ValueError("Invalid or empty response from OpenAI embeddings API")

            embedding = response.data[0].embedding
            if not embedding or len(embedding) == 0:
                raise ValueError("Empty embedding returned from OpenAI API")

            logger.debug(f"✅ Generated embedding with {len(embedding)} dimensions")
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


def perform_completion(
    messages: Union[str, Sequence[Any], Dict[str, Any]],
    response_model: Optional[Type[BaseModel]] = None,
    tools: Optional[Union[Dict[str, Any], Sequence[Any]]] = None,
    model: Optional[str] = None,
    response_token_reserve: Optional[int] = None,
    stream: bool = False,
    config: Optional[Dict[str, Any]] = None,
) -> Union[str, BaseModel, Iterable[str]]:
    """
    Perform a completion using OpenAI or LangSmith endpoints.
    - If tools/functions are provided, returns a string (OpenAI chat completion message content).
    - If streaming, returns an Iterable[str].
    - If using LangSmith with a response_model, returns a BaseModel.

    Args:
        messages: The messages to send to the model
        response_model: Optional Pydantic model for structured output
        tools: Optional tools/functions to make available
        model: The model to use
        response_token_reserve: Token reserve for response
        stream: Whether to stream the response
        config: Optional RunnableConfig for trace context propagation
    """
    # reserve tokens for the model's response
    response_token_reserve = response_token_reserve or DEFAULT_RESPONSE_TOKEN_RESERVE

    # determine the model
    model = model or DEFAULT_MODEL

    logger.debug(
        f"🚀 Starting completion: model={model}, stream={stream}, tools={tools is not None}, response_model={response_model is not None}"
    )

    # multi-stage RAG if structured input
    if isinstance(messages, dict) and "context" in messages and "question" in messages:
        context_list = messages["context"]
        question = messages["question"]
        instruction = messages.get("instruction", DEFAULT_SYSTEM_PROMPT)
        summarization_model = messages.get(
            "summarization_model", DEFAULT_SUMMARIZATION_MODEL
        )
        max_items = messages.get("max_items_per_chunk", DEFAULT_MAX_ITEMS_PER_CHUNK)

        logger.debug(
            f"📚 Multi-stage RAG: {len(context_list)} context items, {max_items} items per chunk"
        )

        # chunk context by object boundaries
        chunks = [
            context_list[i : i + max_items]
            for i in range(0, len(context_list), max_items)
        ]

        # summarize each chunk
        summaries = []
        template = _env.get_template("summarize_context.jinja2")
        for i, chunk in enumerate(chunks):
            logger.debug(
                f"📝 Summarizing chunk {i+1}/{len(chunks)} ({len(chunk)} items)"
            )
            prompt_content = template.render(context=chunk)
            summary = perform_completion(
                messages=prompt_content,
                model=summarization_model,
                response_token_reserve=response_token_reserve,
                config=config,  # Pass config through for trace context
            )
            summaries.append(summary)

        # merge summaries
        merged = "\n\n".join(summaries)
        logger.debug(f"📝 Merged {len(summaries)} summaries into final context")

        # build final messages
        msgs = [
            {"role": "system", "content": instruction},
            {"role": "user", "content": merged},
            {"role": "user", "content": question},
        ]
    else:
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
    total_tokens = _count_message_tokens(msgs, model)
    logger.debug(
        f"🔢 Tokens: {total_tokens:,} + {response_token_reserve:,} reserve = {total_tokens + response_token_reserve:,} (limit: {MODEL_TOKEN_LIMITS[model]:,})"
    )

    if total_tokens + response_token_reserve > MODEL_TOKEN_LIMITS[model]:
        raise RuntimeError(
            f"Prompt too large: needs {total_tokens + response_token_reserve:,} tokens (limit {MODEL_TOKEN_LIMITS[model]:,})."
        )

    # initialize client
    client = _get_client()

    # STREAMING MODE (no response_model, no tools)
    if stream:
        logger.debug(f"🌊 Streaming completion with {model}")

        def _stream_tokens():
            params = {
                "model": model or DEFAULT_MODEL,
                "messages": msgs,
                "stream": True,
            }
            for chunk in client.chat.completions.create(**params):
                token = chunk.choices[0].delta.content or ""
                yield token

        return _stream_tokens()

    # If tools provided, call OpenAI Chat Completions endpoint
    if tools is not None:
        # If tools is a dict, convert to a list of tool definitions
        if isinstance(tools, dict):
            tools_list = list(tools.values())
        else:
            tools_list = tools

        # Use the modern tools format instead of deprecated functions
        params = {
            "model": model,
            "messages": msgs,
            "tools": tools_list,
            "tool_choice": "auto",
        }
        chat_resp = client.chat.completions.create(**params)
        if chat_resp is None:
            return ""

        # Return the full message object instead of just content when tools are used
        if chat_resp.choices and chat_resp.choices[0].message:
            message = chat_resp.choices[0].message
            # Convert to dict format for consistency
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

    # Fallback to LangSmith responses endpoint
    kwargs: Dict[str, Any] = {
        "model": model,
        "input": msgs,
    }

    # Apply trace context configuration if provided
    if config is not None:
        # Extract metadata from config for LangSmith
        metadata = config.get("metadata", {})

        if metadata:
            # Convert any non-string values to strings for LangSmith API compatibility
            processed_metadata = {}
            for key, value in metadata.items():
                if isinstance(value, (int, float, bool)):
                    processed_metadata[key] = str(value)
                elif isinstance(value, (list, tuple)):
                    processed_metadata[key] = str(value)
                else:
                    processed_metadata[key] = value

            kwargs["metadata"] = processed_metadata

    if response_model:
        kwargs["text_format"] = response_model
        resp = client.responses.parse(**kwargs)
        return resp.output_parsed if resp.output_parsed is not None else ""
    else:
        resp = client.responses.create(**kwargs)
        return resp.output if resp.output is not None else ""
