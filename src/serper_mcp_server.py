from dotenv import load_dotenv
from pathlib import Path
# --- Load Environment Variables ---
# Explicitly load the .env file from the project root
dotenv_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=dotenv_path, override=True)

import asyncio
import http.client
import json
import os
import argparse  # Added for command-line arguments
import re
import html
from typing import Optional, Dict, Any, Union, Literal, cast, Annotated, List, Tuple, Set

import openai
import networkx as nx
import pandas as pd
from pydantic import Field
import difflib
from fastmcp import FastMCP, Context

# --- OpenAI Client ---
# The user must have OPENAI_API_KEY set in their environment
# for this to work.

# --- Constants ---
SERPER_GOOGLE_SEARCH_HOST = "google.serper.dev"
SERPER_SCRAPE_HOST = "scrape.serper.dev"
SERPER_API_KEY_ENV_VAR = "SERPER_API_KEY"


# --- Custom Exception ---
class SerperApiClientError(Exception):
    """Custom exception for Serper API client errors."""

    pass


# --- Private Helper Function ---
def _get_resolved_api_key(api_key: Optional[str]) -> str:
    """Resolves the API key from argument or environment variable."""
    resolved_key = api_key if api_key is not None else os.getenv(SERPER_API_KEY_ENV_VAR)
    if not resolved_key:
        raise SerperApiClientError(
            f"Serper API key is missing. Please provide it as an argument or set the '{SERPER_API_KEY_ENV_VAR}' environment variable."
        )
    return resolved_key


def _make_serper_request(
    host: str,
    path: str,
    payload: Union[Dict[str, Any], List[Dict[str, Any]]],
    api_key: Optional[str] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Makes a POST request to a Serper API endpoint.

    Args:
        host: The API host (e.g., "google.serper.dev").
        path: The API path (e.g., "/search" or "/").
        payload: The JSON payload for the request. Can be a single dict or a list of dicts for batch requests.
        api_key: The Serper API key. If None, uses SERPER_API_KEY_ENV_VAR.

    Returns:
        A dictionary or list of dictionaries representing the parsed JSON response.

    Raises:
        SerperApiClientError: For API key issues, network errors,
                              non-2xx responses, or JSON decoding failures.
    """
    resolved_api_key = _get_resolved_api_key(api_key)

    headers = {"X-API-KEY": resolved_api_key, "Content-Type": "application/json"}

    conn: Optional[http.client.HTTPSConnection] = None
    try:
        conn = http.client.HTTPSConnection(host)
        conn.request("POST", path, json.dumps(payload), headers)
        res = conn.getresponse()
        response_data_bytes = res.read()
    except http.client.HTTPException as e:
        raise SerperApiClientError(
            f"HTTP client error during API request to {host}{path}: {e}"
        )
    except ConnectionError as e:
        raise SerperApiClientError(f"Network connection error to {host}{path}: {e}")
    except (
        Exception
    ) as e:  # Catching a broader set of potential issues during the request
        raise SerperApiClientError(
            f"An unexpected error occurred during API request to {host}{path}: {e}"
        )
    finally:
        if conn:
            conn.close()

    try:
        response_data_str = response_data_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise SerperApiClientError(
            f"Failed to decode API response from {host}{path} (not UTF-8): {e}"
        )

    if not (200 <= res.status < 300):
        error_message = (
            f"API request to {host}{path} failed with status {res.status}: {res.reason}. "
            f"Response: {response_data_str[:500]}"  # Limit response preview in error
        )
        raise SerperApiClientError(error_message)

    try:
        return json.loads(response_data_str)
    except json.JSONDecodeError as e:
        raise SerperApiClientError(
            f"Failed to decode JSON response from {host}{path}: {e}. Response: {response_data_str[:500]}"
        )


def _transform_github_url_to_raw(url: str) -> str:
    """
    Transforms a standard GitHub file URL into its raw.githubusercontent.com equivalent.
    If the URL is not a match, it returns the original URL.
    
    Example:
        "https://github.com/owner/repo/blob/main/README.md"
    Becomes:
        "https://raw.githubusercontent.com/owner/repo/main/README.md"
    """
    # Regex to capture the owner, repo, branch, and file path from a GitHub URL
    github_pattern = r"https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)"
    match = re.match(github_pattern, url)
    
    if match:
        owner, repo, branch, file_path = match.groups()
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}"
        return raw_url
        
    return url
 
def _clean_markdown(markdown: str) -> str:
    """
    Cleans the scraped markdown content to be more LLM-friendly.
    - Unescapes HTML entities (e.g., & -> &).
    """
    if not isinstance(markdown, str):
        return ""
    # 1. Unescape HTML entities like &, <, etc.
    cleaned_markdown = html.unescape(markdown)
    # 2. Remove backslash escapes from common markdown characters.
    # This handles cases like \*, \_, \[, \], etc.
    cleaned_markdown = re.sub(r'\\([!\"#$%&\'()*+,-./:;<=>?@\[\\\]^_`{|}~])', r'\1', cleaned_markdown)
    return cleaned_markdown
 
# --- Public API Functions (from user provided code) ---
def query_serper_api(
    queries: Union[str, List[str]],
    api_key: Optional[str] = None,
    search_endpoint: str = "search",
    location: Optional[str] = None,
    num_results: Optional[int] = None,
    autocorrect: Optional[bool] = None,
    time_period_filter: Optional[str] = None,
    page_number: Optional[int] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Queries the Serper.dev Search API (google.serper.dev for /search, /news, /scholar).
    Can handle a single query (str) or multiple queries in a batch (List[str]).
    """
    if search_endpoint not in ["search", "news", "scholar"]:
        raise SerperApiClientError(
            f"Invalid search_endpoint: '{search_endpoint}'. Must be 'search', 'news', or 'scholar'."
        )

    def create_query_payload(query_text: str) -> Dict[str, Union[str, int, bool]]:
        payload: Dict[str, Union[str, int, bool]] = {"q": query_text}
        if location is not None:
            payload["location"] = location
        if num_results is not None:
            payload["num"] = num_results
        # Default autocorrect to False if not specified, otherwise use the provided value.
        payload["autocorrect"] = False if autocorrect is None else autocorrect

        if time_period_filter is not None:
            payload["tbs"] = time_period_filter
        if page_number is not None:
            payload["page"] = page_number
        return payload

    if isinstance(queries, str):
        request_payload = create_query_payload(queries)
    else:  # It's a list of strings
        request_payload = [create_query_payload(q) for q in queries]

    return _make_serper_request(
        host=SERPER_GOOGLE_SEARCH_HOST,
        path=f"/{search_endpoint}",
        payload=request_payload,
        api_key=api_key,
    )


def scrape_serper_url(
    url_to_scrape: str, api_key: Optional[str] = None, include_markdown: bool = True
) -> Dict[str, Any]:
    """
    Scrapes a webpage using the Serper.dev Scrape API (scrape.serper.dev).
    """
    payload: Dict[str, Union[str, bool]] = {
        "url": url_to_scrape,
        "includeMarkdown": include_markdown,
    }

    response = _make_serper_request(
        host=SERPER_SCRAPE_HOST, path="/", payload=payload, api_key=api_key
    )
    # The scrape API does not support batching, so the response is always a dictionary.
    return cast(Dict[str, Any], response)


# --- FastMCP Server Definition ---
mcp: FastMCP = FastMCP(
    name="SerperDevMCPServer",
    instructions="""This server provides tools to interact with Serper.dev's Google Search, Google News, and Google Scholar APIs.
It relies on the SERPER_API_KEY environment variable being set on the server machine for authentication with Serper.dev.
Each tool performs a single query. For multiple distinct queries, call the respective tool multiple times.
Tool annotations like 'readOnlyHint': true, 'idempotentHint': true, 'openWorldHint': true generally apply to these search tools.""",
    mask_error_details=True,  # Mask internal error details from clients
)

# --- MCP Tool Definitions ---


@mcp.tool()
async def google_search(
    ctx: Context,
    query: Annotated[Union[str, List[str]], Field(description="A single search term or a list of search terms.")],
    location: Annotated[Optional[str], Field(description='The location for the search (e.g., "United States", "London, United Kingdom").')] = None,
    num_results: Annotated[Optional[int], Field(description="Number of results to return (e.g., 10, 20, default is usually 10).")] = None,
    autocorrect: Annotated[Optional[bool], Field(description="Whether to enable or disable query autocorrection. Serper's default for this client is False if not specified.")] = None,
    time_period_filter: Annotated[Optional[str], Field(description='Time-based search filter (e.g., "qdr:h" for past hour, "qdr:d" for past day, "qdr:w" for past week). Corresponds to the \'tbs\' parameter.')] = None,
    page_number: Annotated[Optional[int], Field(description="The page number of results to fetch (e.g., 1, 2).")] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Performs a web search using Google (via Serper.dev).
    This tool can be used for a single query or a batch of queries.
    It relies on the SERPER_API_KEY environment variable for authentication.
    This tool is read-only, generally idempotent (results may change over time due to web updates), and interacts with the open web.

    Returns:
        A dictionary for a single query or a list of dictionaries for batch queries.
        In case of an error from the Serper API, a SerperApiClientError will be raised.
    """
    try:
        await ctx.info(
            f"google_search called with query(s): '{query}', location: {location}, num_results: {num_results}, autocorrect: {autocorrect}, time_period_filter: {time_period_filter}, page_number: {page_number}"
        )
        return query_serper_api(
            queries=query,
            api_key=None,  # Ensures environment variable SERPER_API_KEY is used
            search_endpoint="search",
            location=location,
            num_results=num_results,
            autocorrect=autocorrect,
            time_period_filter=time_period_filter,
            page_number=page_number,
        )
    except SerperApiClientError as e:
        await ctx.error(f"Serper API error in google_search for query '{query}': {e}")
        raise
    except Exception as e:
        await ctx.error(f"Unexpected error in google_search for query '{query}': {e}")
        # Re-raise as SerperApiClientError to ensure consistent error type from this layer if not already one
        if not isinstance(e, SerperApiClientError):
            raise SerperApiClientError(
                f"An unexpected error occurred in google_search tool: {e}"
            ) from e
        raise


@mcp.tool()
async def news_search(
    ctx: Context,
    query: Annotated[Union[str, List[str]], Field(description='A single news search term or a list of search terms (e.g., "latest AI advancements", "tech earnings").')],
    location: Annotated[Optional[str], Field(description='The location for the news search (e.g., "United States").')] = None,
    num_results: Annotated[Optional[int], Field(description="Number of news articles to return.")] = None,
    autocorrect: Annotated[Optional[bool], Field(description="Whether to enable or disable query autocorrection.")] = None,
    time_period_filter: Annotated[Optional[str], Field(description='Time-based search filter (e.g., "qdr:h1" for past hour, "qdr:d1" for past day).')] = None,
    page_number: Annotated[Optional[int], Field(description="The page number of news results to fetch.")] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Fetches news articles using Google News.
    This tool can be used for a single query or a batch of queries.
    It relies on the SERPER_API_KEY environment variable for authentication.
    This tool is read-only, generally idempotent (news results change frequently), and interacts with the open web.

    Returns:
        A dictionary for a single query or a list of dictionaries for batch queries.
        In case of an error from the Serper API, a SerperApiClientError will be raised.
    """
    try:
        await ctx.info(
            f"news_search called with query(s): '{query}', location: {location}, num_results: {num_results}, autocorrect: {autocorrect}, time_period_filter: {time_period_filter}, page_number: {page_number}"
        )
        return query_serper_api(
            queries=query,
            api_key=None,  # Ensures environment variable SERPER_API_KEY is used
            search_endpoint="news",
            location=location,
            num_results=num_results,
            autocorrect=autocorrect,
            time_period_filter=time_period_filter,
            page_number=page_number,
        )
    except SerperApiClientError as e:
        await ctx.error(f"Serper API error in news_search for query '{query}': {e}")
        raise
    except Exception as e:
        await ctx.error(f"Unexpected error in news_search for query '{query}': {e}")
        if not isinstance(e, SerperApiClientError):
            raise SerperApiClientError(
                f"An unexpected error occurred in news_search tool: {e}"
            ) from e
        raise


@mcp.tool()
async def scholar_search(
    ctx: Context,
    query: Annotated[Union[str, List[str]], Field(description='A single scholar search term or a list of search terms (e.g., "quantum computing algorithms", "machine learning in healthcare").')],
    num_results: Annotated[Optional[int], Field(description="Number of scholar articles to return.")] = None,
    time_period_filter: Annotated[Optional[str], Field(description='Time-based search filter for scholar articles (e.g., "as_ylo=2020" for articles from 2020 onwards). Corresponds to \'tbs\'.')] = None,
    page_number: Annotated[Optional[int], Field(description="The page number of scholar results to fetch.")] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Fetches academic/scholar articles using Google Scholar (via Serper.dev).
    This tool can be used for a single query or a batch of queries.
    It relies on the SERPER_API_KEY environment variable for authentication.
    This tool is read-only, generally idempotent (results may change over time), and interacts with the open web.

    Returns:
        A dictionary for a single query or a list of dictionaries for batch queries.
        In case of an error from the Serper API, a SerperApiClientError will be raised.
    """
    try:
        await ctx.info(
            f"scholar_search called with query(s): '{query}', num_results: {num_results}, time_period_filter: {time_period_filter}, page_number: {page_number}"
        )
        return query_serper_api(
            queries=query,
            api_key=None,  # Ensures environment variable SERPER_API_KEY is used
            search_endpoint="scholar",
            num_results=num_results,
            time_period_filter=time_period_filter,
            page_number=page_number,
        )
    except SerperApiClientError as e:
        await ctx.error(f"Serper API error in scholar_search for query '{query}': {e}")
        raise
    except Exception as e:
        await ctx.error(f"Unexpected error in scholar_search for query '{query}': {e}")
        if not isinstance(e, SerperApiClientError):
            raise SerperApiClientError(
                f"An unexpected error occurred in scholar_search tool: {e}"
            ) from e
        raise

def _process_and_clean_results(data: Any) -> Any:
    """
    Recursively processes search results to truncate base64 image URLs.
    """
    if isinstance(data, dict):
        # If the key 'imageUrl' exists and its value starts with 'data:image', truncate it.
        if 'imageUrl' in data and isinstance(data['imageUrl'], str) and data['imageUrl'].startswith('data:image'):
            data['imageUrl'] = "[Truncated base64 image data]"
        
        # Recursively process the rest of the dictionary
        return {k: _process_and_clean_results(v) for k, v in data.items()}
    
    elif isinstance(data, list):
        # Recursively process each item in the list
        return [_process_and_clean_results(item) for item in data]
        
    else:
        # Return the data item as is if it's not a dict or list
        return data

async def _perform_single_type_super_search(
    ctx: Context,
    queries: List[str],
    search_type: Literal["search", "news", "scholar"],
    max_related_searches: int,
    max_depth: int,
    location: Optional[str],
    num_results: Optional[int],
    autocorrect: Optional[bool],
    time_period_filter: Optional[str],
) -> Tuple[Dict[str, Any], int]:
    """Helper to perform a super search for a single search type."""
    all_results: Dict[str, Any] = {}
    queries_to_process = list(queries)
    processed_queries: Set[str] = set()

    for depth in range(max_depth + 1):
        if not queries_to_process:
            break

        current_queries = [q for q in queries_to_process if q not in processed_queries]
        if not current_queries:
            break

        await ctx.info(f"Super search (type: {search_type}, depth {depth}): processing {len(current_queries)} queries: {current_queries}")
        processed_queries.update(current_queries)
        queries_to_process = []

        try:
            results = query_serper_api(
                queries=current_queries,
                api_key=None,
                search_endpoint=search_type,
                location=location,
                num_results=num_results,
                autocorrect=autocorrect,
                time_period_filter=time_period_filter,
            )
            
            # Clean the results to remove base64 image data before casting
            cleaned_results = _process_and_clean_results(results)
            result_list = cast(List[Dict[str, Any]], cleaned_results)

            for result in result_list:
                if not isinstance(result, dict):
                    await ctx.warning(f"Skipping non-dict item in search results: {result}")
                    continue

                original_query = result.get("searchParameters", {}).get("q")
                if original_query:
                    all_results[original_query] = result

                if max_related_searches > 0 and depth < max_depth:
                    related_searches = result.get("relatedSearches", [])
                    if isinstance(related_searches, list):
                        for i, related in enumerate(related_searches):
                            if i < max_related_searches:
                                related_query = related.get("query")
                                if related_query and related_query not in processed_queries:
                                    queries_to_process.append(related_query)
        except SerperApiClientError as e:
            await ctx.error(f"Serper API error during super_search (type: {search_type}, depth {depth}): {e}")
            break
        except Exception as e:
            await ctx.error(f"Unexpected error during super_search (type: {search_type}, depth {depth}): {e}")
            break
            
    return all_results, len(processed_queries)


@mcp.tool()
async def super_search(
    ctx: Context,
    queries: Annotated[List[str], Field(description="A list of initial search terms or questions.")],
    search_types: Annotated[Union[Literal["search", "news", "scholar"], List[Literal["search", "news", "scholar"]]], Field(description="A search type or a list of search types to perform.")] = "search",
    max_related_searches: Annotated[int, Field(description="The maximum number of related searches to follow from each result set. Set to 0 to disable recursive searching.", ge=0)] = 3,
    max_depth: Annotated[int, Field(description="The maximum recursion depth for following related searches.", ge=1, le=5)] = 1,
    location: Annotated[Optional[str], Field(description='The location for the search (e.g., "United States", "London, United Kingdom").')] = None,
    num_results: Annotated[Optional[int], Field(description="Number of results to return for each query (e.g., 10, 20).")] = None,
    autocorrect: Annotated[Optional[bool], Field(description="Whether to enable or disable query autocorrection.")] = None,
    time_period_filter: Annotated[Optional[str], Field(description='Time-based search filter (e.g., "qdr:d" for past day).')] = None,
) -> Dict[str, Any]:
    """
    Performs a recursive, multi-query search using Google, News, or Scholar.
    Can perform searches across multiple types (e.g., 'search' and 'news') in a single call.

    This tool takes an initial list of queries, executes them for each specified search type,
    and then recursively fetches results for the top related searches found in the results,
    up to a specified depth. All results are aggregated by search type.
    """
    if isinstance(search_types, str):
        search_types_list = [search_types]
    else:
        search_types_list = search_types

    all_results: Dict[str, Any] = {}
    total_queries_processed = 0

    # Use asyncio.gather to run searches for different types concurrently
    search_tasks = []
    for s_type in search_types_list:
        task = _perform_single_type_super_search(
            ctx=ctx,
            queries=queries,
            search_type=cast(Literal["search", "news", "scholar"], s_type),
            max_related_searches=max_related_searches,
            max_depth=max_depth,
            location=location,
            num_results=num_results,
            autocorrect=autocorrect,
            time_period_filter=time_period_filter,
        )
        search_tasks.append(task)

    try:
        results_per_type = await asyncio.gather(*search_tasks)
        
        for i, (type_results, queries_processed_for_type) in enumerate(results_per_type):
            s_type = search_types_list[i]
            all_results[s_type] = type_results
            total_queries_processed += queries_processed_for_type

    except Exception as e:
        await ctx.error(f"An error occurred during concurrent super_search execution: {e}")
        # Fallback or partial results might be handled here if needed
        
    return {"aggregated_results": all_results, "total_queries_processed": total_queries_processed}

@mcp.tool()
async def scrape_url(
    ctx: Context,
    url: Annotated[str, Field(description="The URL of the webpage to scrape and extract Markdown from.")],
) -> str:
    """
    Fetches and extracts the Markdown content from a given URL.
    If a GitHub file URL is provided, it will be automatically converted to its raw version for scraping.
    This tool uses the Serper.dev Scrape API to get the content.
    It relies on the SERPER_API_KEY environment variable for authentication.
    This tool is read-only and interacts with the open web.

    Returns:
        A string containing the Markdown content of the webpage.
        If the API call is successful but no Markdown is returned, an empty string is provided.
        In case of an error from the Serper API, a SerperApiClientError will be raised.
    """
    try:
        await ctx.info(f"scrape_url called with original url: '{url}'")
        
        # Transform GitHub URLs to their raw equivalent
        transformed_url = _transform_github_url_to_raw(url)
        if transformed_url != url:
            await ctx.info(f"Transformed GitHub URL to: '{transformed_url}'")

        # The scrape_serper_url function handles the actual API call.
        response_data = scrape_serper_url(
            url_to_scrape=transformed_url,
            api_key=None,  # Ensures environment variable is used
            include_markdown=True,
        )

        # Per the requirement, we only return the 'markdown' field.
        markdown_content = response_data.get("markdown", "")
        
        # Clean the markdown to remove unnecessary escapes
        cleaned_markdown = _clean_markdown(markdown_content)
        return cleaned_markdown

    except SerperApiClientError as e:
        await ctx.error(f"Serper API error in scrape_url for url '{url}': {e}")
        raise
    except Exception as e:
        await ctx.error(f"Unexpected error in scrape_url for url '{url}': {e}")
        if not isinstance(e, SerperApiClientError):
            raise SerperApiClientError(
                f"An unexpected error occurred in scrape_url tool: {e}"
            ) from e
        raise

def _resolve_entities_with_splink(
    extracted_relationships: List[Dict[str, Any]]
) -> Dict[str, str]:
    """
    Uses string similarity to perform entity resolution and returns a mapping from
    original entity names to a canonical name. This is a simpler, more reliable
    approach than complex probabilistic record linkage for our use case.
    """
    unique_entities = set()
    for item in extracted_relationships:
        unique_entities.add(item['source'])
        unique_entities.add(item['target'])

    if not unique_entities:
        return {}

    entities_list = list(unique_entities)
    canonical_mapping = {}
    
    # Initialize each entity to map to itself
    for entity in entities_list:
        canonical_mapping[entity] = entity
    
    # Use Union-Find data structure to group similar entities
    def find_canonical(entity):
        if canonical_mapping[entity] != entity:
            canonical_mapping[entity] = find_canonical(canonical_mapping[entity])
        return canonical_mapping[entity]
    
    def union_entities(entity1, entity2):
        canonical1 = find_canonical(entity1)
        canonical2 = find_canonical(entity2)
        
        if canonical1 != canonical2:
            # Choose the longer name as the canonical representative
            if len(canonical1) >= len(canonical2):
                canonical_mapping[canonical2] = canonical1
            else:
                canonical_mapping[canonical1] = canonical2
    
    # Compare all pairs of entities for similarity
    for i in range(len(entities_list)):
        for j in range(i + 1, len(entities_list)):
            entity1 = entities_list[i]
            entity2 = entities_list[j]
            
            # Normalize for comparison (lowercase, strip whitespace)
            norm1 = entity1.lower().strip()
            norm2 = entity2.lower().strip()
            
            # Calculate similarity using different metrics
            sequence_similarity = difflib.SequenceMatcher(None, norm1, norm2).ratio()
            
            # Check for various matching patterns
            is_similar = False
            
            # High sequence similarity
            if sequence_similarity >= 0.85:
                is_similar = True
            
            # One is a substring of the other (after normalization)
            elif norm1 in norm2 or norm2 in norm1:
                # But only if the shorter one is at least 3 characters and
                # represents at least 60% of the longer one
                shorter_len = min(len(norm1), len(norm2))
                longer_len = max(len(norm1), len(norm2))
                if shorter_len >= 3 and shorter_len / longer_len >= 0.6:
                    is_similar = True
            
            # Similar after removing common prefixes/suffixes like "The", "Sir", etc.
            else:
                # Remove common prefixes and suffixes
                prefixes_to_remove = ['the ', 'sir ', 'dr ', 'prof ', 'mr ', 'ms ', 'mrs ']
                suffixes_to_remove = [' inc', ' corp', ' company', ' ltd', ' llc']
                
                clean1 = norm1
                clean2 = norm2
                
                for prefix in prefixes_to_remove:
                    if clean1.startswith(prefix):
                        clean1 = clean1[len(prefix):]
                    if clean2.startswith(prefix):
                        clean2 = clean2[len(prefix):]
                
                for suffix in suffixes_to_remove:
                    if clean1.endswith(suffix):
                        clean1 = clean1[:-len(suffix)]
                    if clean2.endswith(suffix):
                        clean2 = clean2[:-len(suffix)]
                
                clean_similarity = difflib.SequenceMatcher(None, clean1, clean2).ratio()
                if clean_similarity >= 0.9:
                    is_similar = True
            
            if is_similar:
                union_entities(entity1, entity2)
    
    # Ensure all entities point to their canonical representative
    final_mapping = {}
    for entity in entities_list:
        final_mapping[entity] = find_canonical(entity)
    
    return final_mapping


def _is_valid_entity(entity_name: str) -> bool:
    """Filter out low-quality entities."""
    if not entity_name or len(entity_name) < 3:
        return False
    
    # Filter out common noise patterns
    noise_patterns = [
        r'^\d+\.',  # List markers like "1.", "2."
        r'^\d+%$',  # Percentages like "21.3%"
        r'^\d+$',   # Pure numbers
        r'^[a-zA-Z]$',  # Single letters
    ]
    
    for pattern in noise_patterns:
        if re.match(pattern, entity_name.strip()):
            return False
    
    # Filter out common stopwords/generic terms
    stopwords = {
        'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
        'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before',
        'after', 'above', 'below', 'between', 'among', 'this', 'that', 'these',
        'those', 'it', 'they', 'them', 'their', 'there', 'here', 'where', 'when',
        'increase', 'improve', 'develop', 'support', 'related', 'concept', 'thing'
    }
    
    if entity_name.lower().strip() in stopwords:
        return False
        
    return True

def _linearize_graph_for_llm(graph: nx.DiGraph) -> str:
    """
    Serializes the graph into a centrality-ordered string for LLM consumption.
    """
    if not graph.nodes:
        return "The knowledge graph is empty."

    # Sort nodes by degree centrality
    sorted_nodes = sorted(
        graph.nodes(data=True),
        key=lambda x: x[1].get('centrality', {}).get('degree', 0),
        reverse=True
    )

    linearized_representation = []
    linearized_representation.append("### Knowledge Graph Summary (Ordered by Importance)\n")

    for node, data in sorted_nodes:
        node_info = f"- **Entity:** {node} (Type: {data.get('type', 'Unknown')})"
        linearized_representation.append(node_info)

        # Add outgoing relationships
        outgoing_edges = list(graph.out_edges(node, data=True))
        if outgoing_edges:
            linearized_representation.append("  - **Connects To:**")
            for _, target, edge_data in outgoing_edges:
                linearized_representation.append(f"    - {edge_data.get('label', 'related to')} -> {target} (Strength: {edge_data.get('weight', 0):.2f})")

        # Add incoming relationships
        incoming_edges = list(graph.in_edges(node, data=True))
        if incoming_edges:
            linearized_representation.append("  - **Is Connected From:**")
            for source, _, edge_data in incoming_edges:
                linearized_representation.append(f"    - {source} -> {edge_data.get('label', 'related to')} (Strength: {edge_data.get('weight', 0):.2f})")
    
    return "\n".join(linearized_representation)

async def _summarize_entity(
    ctx: Context,
    openai_client: openai.AsyncOpenAI,
    i: int,
    total_nodes: int,
    node_data: tuple,
    graph_context: str
) -> Optional[dict]:
    """Summarize a single entity asynchronously using the linearized graph context."""
    node, data = node_data
    try:
        await ctx.info(f"Summarizing entity {i+1}/{total_nodes}: {node}")
        
        prompt = f"""Given the following knowledge graph summary:

{graph_context}

Provide a concise 2-3 sentence summary of the entity '{node}', focusing on its role, significance, and key relationships within the topic.
Do not simply list its connections; synthesize the information into a coherent description."""

        await ctx.info(f"Making OpenAI API call for entity summary {i+1} (model: gpt-4.1-nano)")
        response = await openai_client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes entities from a knowledge graph."},
                {"role": "user", "content": prompt}
            ]
        )
        await ctx.info(f"OpenAI API call completed for entity summary {i+1}")
        
        if response.choices and response.choices[0].message.content:
            await ctx.info(f"Successfully summarized entity {i+1}: {node}")
            return {
                "entity": node,
                "summary": response.choices[0].message.content
            }
        else:
            await ctx.warning(f"No response content for entity {node}")
            return None
    except Exception as e:
        await ctx.warning(f"Failed to summarize entity {node}. Reason: {e}")
        return None

@mcp.tool()
async def analyze_topic(
    ctx: Context,
    query: Annotated[str, Field(description="The user's topic of interest (e.g., 'The impact of AI on healthcare').")],
    search_depth: Annotated[int, Field(description="The recursion depth for the initial super_search (default: 2).", ge=1, le=5)] = 2,
    max_urls_per_query: Annotated[int, Field(description="The number of top search results to scrape for each query (default: 3).", ge=1)] = 3,
    search_types: Annotated[List[Literal["search", "news", "scholar"]], Field(description="A list of search types to perform.")] = ["search", "news"],
    chunk_size: Annotated[int, Field(description="The size of text chunks for processing.", ge=100)] = 600,
    chunk_overlap: Annotated[int, Field(description="The overlap size between text chunks.", ge=0)] = 100,
    max_entities_per_chunk: Annotated[int, Field(description="The maximum number of entities to extract per chunk.", ge=1)] = 10,
    allowed_entity_types: Annotated[List[str], Field(description="A list of entity types to focus on during extraction.")] = ["Person", "Organization", "Technology", "Concept", "Location"],
) -> Dict[str, Any]:
    """
    Provides a comprehensive, multi-layered analysis of a given topic by dynamically building and querying a knowledge graph from web search results.
    """
    original_query = query
    await ctx.info(f"Starting topic analysis for query: '{original_query}'")

    # Phase 1: Document Collection & Ingestion
    await ctx.info("Phase 1: Kicking off document collection with super_search.")
    
    # For the initial implementation, we will just call super_search and return the results
    # to smoke test the first part of the pipeline.
    search_results = await super_search(
        ctx=ctx,
        queries=[original_query],
        search_types=search_types,
        max_depth=search_depth,
        # Limiting related searches for now to keep the initial run focused.
        max_related_searches=2,
    )

    # Phase 2: Content Scraping
    await ctx.info("Phase 2: Starting content scraping.")
    
    urls_to_scrape = set()
    for search_type, results in search_results.get("aggregated_results", {}).items():
        for query, result_data in results.items():
            # Process organic results
            for item in result_data.get("organic", []):
                if len(urls_to_scrape) < max_urls_per_query:
                    urls_to_scrape.add(item.get("link"))
            # Process news results
            for item in result_data.get("news", []):
                if len(urls_to_scrape) < max_urls_per_query:
                    urls_to_scrape.add(item.get("link"))
            # Process scholar results
            for item in result_data.get("scholar", []):
                if len(urls_to_scrape) < max_urls_per_query:
                    urls_to_scrape.add(item.get("link"))

    await ctx.info(f"Found {len(urls_to_scrape)} unique URLs to scrape.")

    scraped_content = []
    urls_list = list(urls_to_scrape)
    await ctx.info(f"Starting parallel scraping of {len(urls_list)} URLs")
    
    async def scrape_single_url(i: int, url: str) -> Optional[dict]:
        """Scrape a single URL asynchronously."""
        if not url:
            return None
        try:
            await ctx.info(f"Scraping URL {i+1}/{len(urls_list)}: {url}")
            content = await scrape_url(ctx, url)
            if content:
                await ctx.info(f"Successfully scraped URL {i+1}: {len(content)} characters")
                return {"url": url, "content": content}
            else:
                await ctx.warning(f"URL {i+1} returned empty content: {url}")
                return None
        except Exception as e:
            await ctx.warning(f"Failed to scrape URL {i+1}: {url}. Reason: {e}")
            return None
    
    # Process all URLs in parallel using asyncio.gather
    scraping_tasks = [scrape_single_url(i, url) for i, url in enumerate(urls_list)]
    scraping_results = await asyncio.gather(*scraping_tasks, return_exceptions=True)
    
    # Filter out None results and exceptions
    for result in scraping_results:
        if result is not None and not isinstance(result, Exception):
            scraped_content.append(result)
    
    await ctx.info(f"Completed parallel scraping: {len(scraped_content)} successful scrapes")

    # Phase 3: Document-Level Knowledge Extraction
    await ctx.info("Phase 3: Starting document-level knowledge extraction.")

    if not os.getenv("OPENAI_API_KEY"):
        await ctx.error("OPENAI_API_KEY environment variable not set.")
        return {"status": "Error", "message": "OPENAI_API_KEY not set."}

    try:
        openai_client = openai.AsyncOpenAI()
    except openai.OpenAIError as e:
        await ctx.error(f"Error initializing OpenAI client: {e}. Please ensure your OPENAI_API_KEY is valid.")
        return {"status": "Error", "message": f"OpenAI client initialization failed: {e}"}

    # --- RHF (Relation-Head-Facts) Pipeline ---
    
    async def _run_rhf_pipeline_on_document(document_text: str) -> List[Dict[str, Any]]:
        """Runs the full RHF pipeline on a single document and returns extracted relationships."""
        
        # Step 1: Extract Relations
        await ctx.info("RHF Step 1: Extracting relations from document.")
        relations_tools = [
            {
                "type": "function",
                "function": {
                    "name": "store_relations",
                    "description": "Stores the extracted semantic relation types.",
                    "parameters": {
                        "type": "object",
                        "properties": {"relations": {"type": "array", "items": {"type": "string"}}},
                        "required": ["relations"]
                    }
                }
            }
        ]
        relations_prompt = f"""Given the document, identify all unique semantic relation types.
Examples: 'works for', 'located in', 'develops', 'CEO of'.
Return only the relation types, not the entities.

DOCUMENT:
{document_text}"""
        
        try:
            response = await openai_client.chat.completions.create(
                model="gpt-4.1-nano",
                messages=[
                    {"role": "system", "content": "You are an expert in identifying relationship types."},
                    {"role": "user", "content": relations_prompt}
                ],
                tools=cast(Any, relations_tools),
                tool_choice={"type": "function", "function": {"name": "store_relations"}}
            )
            if not (response.choices and response.choices[0].message.tool_calls):
                await ctx.warning("RHF Step 1: No relations found in document.")
                return []
            
            tool_call = response.choices[0].message.tool_calls[0]
            if tool_call.function.name != "store_relations":
                return []
                
            all_relations = json.loads(tool_call.function.arguments).get("relations", [])
            if not all_relations:
                return []
        except Exception as e:
            await ctx.error(f"RHF Step 1 failed: {e}")
            return []

        document_relationships = []
        
        # Step 2 & 3: Extract Head Entities and Facts for each relation
        for relation in all_relations:
            await ctx.info(f"RHF Step 2: Extracting head entities for relation: '{relation}'")
            heads_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "store_head_entities",
                        "description": "Stores extracted head entities for a relation.",
                        "parameters": {
                            "type": "object",
                            "properties": {"head_entities": {"type": "array", "items": {"type": "string"}}},
                            "required": ["head_entities"]
                        }
                    }
                }
            ]
            heads_prompt = f"""Given the document and the relation '{relation}', list all subject entities.

DOCUMENT:
{document_text}"""
            
            try:
                response = await openai_client.chat.completions.create(
                    model="gpt-4.1-nano",
                    messages=[
                        {"role": "system", "content": "You are an expert in identifying subject entities."},
                        {"role": "user", "content": heads_prompt}
                    ],
                    tools=cast(Any, heads_tools),
                    tool_choice={"type": "function", "function": {"name": "store_head_entities"}}
                )
                if not (response.choices and response.choices[0].message.tool_calls):
                    continue
                
                tool_call = response.choices[0].message.tool_calls[0]
                if tool_call.function.name != "store_head_entities":
                    continue
                    
                head_entities = json.loads(tool_call.function.arguments).get("head_entities", [])
            except Exception as e:
                await ctx.error(f"RHF Step 2 failed for relation '{relation}': {e}")
                continue

            for head in head_entities:
                await ctx.info(f"RHF Step 3: Extracting facts for ('{head}', '{relation}', ?)")
                facts_tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": "store_facts",
                            "description": "Stores extracted facts (tail entities and types).",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "facts": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "tail_entity": {"type": "string"},
                                                "tail_entity_type": {"type": "string", "enum": allowed_entity_types}
                                            },
                                            "required": ["tail_entity", "tail_entity_type"]
                                        }
                                    }
                                },
                                "required": ["facts"]
                            }
                        }
                    }
                ]
                facts_prompt = f"""From the document, identify all tail entities that have the relation '{relation}' with the head entity '{head}'.

DOCUMENT:
{document_text}"""
                
                try:
                    response = await openai_client.chat.completions.create(
                        model="gpt-4.1-nano",
                        messages=[
                            {"role": "system", "content": "You are an expert in extracting structured facts."},
                            {"role": "user", "content": facts_prompt}
                        ],
                        tools=cast(Any, facts_tools),
                        tool_choice={"type": "function", "function": {"name": "store_facts"}}
                    )
                    if not (response.choices and response.choices[0].message.tool_calls):
                        continue
                        
                    tool_call = response.choices[0].message.tool_calls[0]
                    if tool_call.function.name != "store_facts":
                        continue
                        
                    facts = json.loads(tool_call.function.arguments).get("facts", [])
                    
                    for fact in facts:
                        tail_entity = fact.get("tail_entity")
                        if tail_entity and _is_valid_entity(head) and _is_valid_entity(tail_entity):
                            document_relationships.append({
                                "source": head,
                                "source_type": "Unknown",
                                "target": tail_entity,
                                "target_type": fact.get("tail_entity_type", "Unknown"),
                                "relationship": relation,
                                "strength": 0.8
                            })
                except Exception as e:
                    await ctx.error(f"RHF Step 3 failed for ('{head}', '{relation}', ?): {e}")
        
        return document_relationships

    # --- Execute RHF Pipeline for each document ---
    parsed_relationships = []
    for i, doc in enumerate(scraped_content):
        content = doc.get("content")
        if content:
            await ctx.info(f"--- Running RHF Pipeline on Document {i+1}/{len(scraped_content)} ---")
            relationships = await _run_rhf_pipeline_on_document(content)
            parsed_relationships.extend(relationships)
            await ctx.info(f"--- Extracted {len(relationships)} relationships from Document {i+1} ---")

    await ctx.info(f"Completed RHF pipeline across all documents. Extracted {len(parsed_relationships)} total relationships.")

    # Phase 4.5: Entity Resolution
    await ctx.info("Phase 4.5: Starting entity resolution.")

    canonical_entity_map = _resolve_entities_with_splink(parsed_relationships)
    await ctx.info(f"Resolved {len(parsed_relationships)} relationships into {len(set(canonical_entity_map.values()))} canonical entities.")

    # Phase 5: Graph Construction
    await ctx.info("Phase 5: Starting graph construction with resolved entities.")
    
    G = nx.DiGraph()

    for rel in parsed_relationships:
        source_canonical = canonical_entity_map.get(rel['source'], rel['source'])
        target_canonical = canonical_entity_map.get(rel['target'], rel['target'])

        # Add nodes with extracted entity types
        source_type = rel.get('source_type', 'Unknown')
        target_type = rel.get('target_type', 'Unknown')
        
        # If node already exists, keep the most specific type (not "Unknown")
        if source_canonical in G.nodes:
            existing_type = G.nodes[source_canonical].get('type', 'Unknown')
            if existing_type == 'Unknown' and source_type != 'Unknown':
                G.nodes[source_canonical]['type'] = source_type
        else:
            G.add_node(source_canonical, type=source_type)
            
        if target_canonical in G.nodes:
            existing_type = G.nodes[target_canonical].get('type', 'Unknown')
            if existing_type == 'Unknown' and target_type != 'Unknown':
                G.nodes[target_canonical]['type'] = target_type
        else:
            G.add_node(target_canonical, type=target_type)
        
        # Add edge with attributes
        G.add_edge(
            source_canonical,
            target_canonical,
            label=rel['relationship'],
            weight=rel['strength']
        )

    # Phase 6: Graph Analysis & Centrality
    await ctx.info("Phase 6: Starting graph analysis with networkx.")

    # Calculate centrality measures
    degree_centrality = nx.degree_centrality(G)
    betweenness_centrality = nx.betweenness_centrality(G, weight='weight')
    closeness_centrality = nx.closeness_centrality(G, distance='weight')

    # Add centrality measures to node attributes
    for node in G.nodes():
        G.nodes[node]['centrality'] = {
            "degree": degree_centrality.get(node, 0),
            "betweenness": betweenness_centrality.get(node, 0),
            "closeness": closeness_centrality.get(node, 0)
        }

    # Phase 7: Summarization
    await ctx.info("Phase 7: Starting summarization.")

    # Identify top N central nodes for summarization
    sorted_nodes = sorted(G.nodes(data=True), key=lambda x: x[1]['centrality']['degree'], reverse=True)
    
    top_nodes = sorted_nodes[:5]  # Summarize top 5 nodes
    await ctx.info(f"Starting parallel summarization of top {len(top_nodes)} entities")

    # Linearize the graph for context
    graph_context_for_llm = _linearize_graph_for_llm(G)
    
    # Process all entity summaries in parallel using asyncio.gather
    summary_tasks = [_summarize_entity(ctx, openai_client, i, len(top_nodes), node_data, graph_context_for_llm) for i, node_data in enumerate(top_nodes)]
    summary_results = await asyncio.gather(*summary_tasks, return_exceptions=True)
    
    # Filter out None results and exceptions
    summaries = []
    for result in summary_results:
        if result is not None and not isinstance(result, Exception):
            summaries.append(result)
    
    await ctx.info(f"Completed parallel summarization: {len(summaries)} successful summaries")

    # Phase 8: Structured Output Generation
    await ctx.info("Phase 8: Generating structured output.")

    # Convert graph to a serializable format
    graph_data = nx.node_link_data(G)

    # Get top 5 central entities
    key_entities = []
    for summary_data in summaries:
        entity_name = summary_data['entity']
        node_data = G.nodes.get(entity_name, {})
        key_entities.append({
            "entity": entity_name,
            "type": node_data.get('type', 'Unknown'),
            "centrality": node_data.get('centrality', {}),
            "summary": summary_data.get('summary', '')
        })

    # Get top 5 relationships by weight
    sorted_edges = sorted(G.edges(data=True), key=lambda x: x[2].get('weight', 0), reverse=True)
    key_relationships = [
        {
            "source": source,
            "target": target,
            "label": data.get('label', 'related_to'),
            "weight": data.get('weight', 0)
        }
        for source, target, data in sorted_edges[:5]
    ]

    return {
        "query": original_query,
        "processing_stats": {
            "urls_scraped": len(scraped_content),
            "documents_processed": len(scraped_content),
            "entities_extracted": len(G.nodes),
            "relationships_found": len(G.edges),
            "communities_detected": 0  # Placeholder for now
        },
        "key_insights": {
            "primary_themes": [],  # Placeholder for now
            "central_entities": key_entities,
            "key_relationships": key_relationships,
            "emerging_patterns": []  # Placeholder for now
        },
        "knowledge_graph": graph_data,
        "sources": {
            "search_queries": [q for r in search_results.get("aggregated_results", {}).values() for q in r.keys()],
            "scraped_urls": [doc['url'] for doc in scraped_content],
            "search_types_used": list(search_results.get("aggregated_results", {}).keys())
        }
    }


async def print_available_tools():
    """Helper async function to print available tools."""
    tools_dict = await mcp.get_tools()
    print(f"Available tools: {[tool_name for tool_name in tools_dict.keys()]}")


if __name__ == "__main__":
    print("Initializing SerperDevMCPServer...", flush=True)

    # Check for Serper API Key
    serper_api_key_present = os.getenv(SERPER_API_KEY_ENV_VAR)
    if not serper_api_key_present:
        print(
            f"WARNING: The '{SERPER_API_KEY_ENV_VAR}' environment variable is not set. Serper API calls will likely fail.",
            flush=True
        )
    else:
        print(f"✅ The '{SERPER_API_KEY_ENV_VAR}' environment variable is set.", flush=True)

    # Check for OpenAI API Key
    openai_api_key_present = os.getenv("OPENAI_API_KEY")
    if not openai_api_key_present:
        print(
            f"WARNING: The 'OPENAI_API_KEY' environment variable is not set. OpenAI calls will fail.",
            flush=True
        )
    else:
        print("✅ The 'OPENAI_API_KEY' environment variable is set.", flush=True)


    print("\nFetching available tools...", flush=True)
    asyncio.run(print_available_tools())

    parser = argparse.ArgumentParser(
        description="Runs the SerperDevMCPServer, allowing interaction with Serper.dev API services (Google Search, News, Scholar) via the Model Context Protocol (MCP).",
        formatter_class=argparse.RawTextHelpFormatter, # Allows for newlines in help text
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "streamable-http", "sse"],
        help=(
            "MCP server transport type.\n"
            "Determines how the server communicates with clients.\n"
            "Options:\n"
            "  stdio: Uses standard input/output (default if not specified).\n"
            "  streamable-http: Uses HTTP for web-based clients.\n"
            "  sse: Uses Server-Sent Events (legacy HTTP).\n"
            "This argument overrides the MCP_SERVER_TRANSPORT environment variable."
        ),
    )
    args = parser.parse_args()

    server_host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    server_port_str = os.getenv("MCP_SERVER_PORT", "8000")
    try:
        server_port = int(server_port_str)
    except ValueError:
        print(
            f"Warning: Invalid MCP_SERVER_PORT value '{server_port_str}'. Defaulting to 8000."
        )
        server_port = 8000

    # Determine transport type: CLI arg > env var > default
    if args.transport:
        raw_transport_type = args.transport
    else:
        raw_transport_type = os.getenv("MCP_SERVER_TRANSPORT", "stdio")

    allowed_transports = {"stdio", "streamable-http", "sse"}
    if raw_transport_type not in allowed_transports:
        print(
            f"Warning: Invalid MCP_SERVER_TRANSPORT value '{raw_transport_type}'. Defaulting to 'stdio'.",
            flush=True
        )
        transport_type = cast(Literal["stdio", "streamable-http", "sse"], "stdio")
    else:
        transport_type = cast(Literal["stdio", "streamable-http", "sse"], raw_transport_type)

    print(f"Attempting to start server with {transport_type.upper()} transport...", flush=True)
    
    try:
        if transport_type != "stdio":
            print(f"Listening on http://{server_host}:{server_port}", flush=True)
            print("Press Ctrl+C to stop the server.", flush=True)
            mcp.run(transport=transport_type, port=server_port, host=server_host)  # type: ignore
        else:
            print("Using STDIO transport.", flush=True)
            print("Press Ctrl+C to stop the server.", flush=True)
            mcp.run(transport=transport_type)  # host and port are not applicable for stdio
    except KeyboardInterrupt:
        print("\nServer shutdown requested by user.")
    except Exception as e:
        print(f"Failed to start server: {e}")
