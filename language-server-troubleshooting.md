Okay, this has been an extensive and multifaceted troubleshooting session. Let's break down the entire process.

**Overall Problem Statement:**

The user initially wanted to configure a Python-based FastMCP server (`serper_mcp_server.py`) to be used via `stdio` transport by their Roo Cline client. This seemingly simple task led to a cascade of issues, including incorrect server startup defaults, crashes when using `stdio`, and then a significant, parallel troubleshooting effort to get the `mcp-language-server` (another MCP tool presumably used for code intelligence within Roo Cline) to correctly recognize symbols in the Python project, especially from the `fastmcp` library itself and project-local definitions.

**Part 1: Configuring and Running `serper_mcp_server.py`**

1.  **Initial Goal:** Make `serper_mcp_server.py` usable via `stdio` transport and add its configuration to `mcp_settings.json`.
    *   **Attempt 1:** The assistant correctly identified the need to specify `command` and `args` for the server in `mcp_settings.json`. It used `context7` to look up `fastMCP` documentation for `stdio` settings.
    *   **Outcome:** The initial `mcp_settings.json` entry was created.
    *   **Problem 1a:** The user reported the server wasn't "popping up". This led to attempts to run the server manually.
    *   **Attempt 1a.1:** Running `uv run python serper_mcp_server.py` revealed the server defaulted to "SSE transport".
    *   **Diagnosis 1a.1:** The server script defaulted to "sse" if `MCP_SERVER_TRANSPORT` was not set.
    *   **Attempt 1a.2:** Running with `MCP_SERVER_TRANSPORT=stdio uv run python serper_mcp_server.py`.
    *   **Outcome 1a.2:** This caused a crash: `FastMCP.run_stdio_async() got an unexpected keyword argument 'port'`.
    *   **Diagnosis 1a.2:** The `serper_mcp_server.py` script always passed `host` and `port` to `mcp.run()`, which is invalid for `stdio` transport.
    *   **Solution 1a (Resolution for basic server run):**
        *   The assistant modified `serper_mcp_server.py` to:
            1.  Default the `MCP_SERVER_TRANSPORT` environment variable to `"stdio"` if not set.
            2.  Conditionally pass `host` and `port` arguments to `mcp.run()` only when the transport type is *not* `"stdio"`.
        *   This successfully allowed the server to run correctly with `stdio` by default and avoided the crash.

2.  **Enhancement: Command-line argument for transport selection.**
    *   **Attempt 2:** The user requested the ability to set the transport type via a command-line argument. The assistant integrated `argparse` into `serper_mcp_server.py` to accept a `--transport` argument, establishing a precedence: CLI argument > environment variable > default. The `--help` message was also improved.
    *   **Outcome 2:** This functionality was successfully added and verified.

3.  **Consistency: Apply changes to `serper_mcp_server_secure.py`.**
    *   **Attempt 3:** The assistant mirrored the `argparse` and transport logic changes to `serper_mcp_server_secure.py`.
    *   **Outcome 3:** Successful.

4.  **Testing: Add tests for new transport selection logic.**
    *   **Attempt 4:** The assistant decided to use `subprocess.run` to test the server scripts with different configurations. Parameterized tests were added to `test_serper_mcp_server.py` for both server scripts.
    *   **Outcome 4a (Initial Failure):** Tests failed due to assertion mismatches. The initial `print()` statements in the server scripts were not reliably captured or were interleaved with `fastmcp` logs.
    *   **Solution 4b (Test Fix):**
        *   Added `flush=True` to all relevant `print()` calls in `serper_mcp_server.py` and `serper_mcp_server_secure.py` to improve output capture reliability in subprocesses.
        *   Adjusted test assertions to look for more reliable log messages from `fastmcp` or Uvicorn for HTTP transports, and specific custom messages for `stdio`.
    *   **Outcome 4b (Success):** All tests (original 10 + 20 new ones for transport selection) passed.

5.  **Refinement: Improve exception messages.**
    *   **Attempt 5:** The user requested a review of exception messages for clarity. The assistant identified the "API key missing" error message in `_get_resolved_api_key` in both server scripts for improvement.
    *   **Outcome 5a:** The message was updated to be more informative (e.g., "Serper API key is missing. Please provide it as an argument or set the '{SERPER_API_KEY_ENV_VAR}' environment variable.").
    *   **Problem 5b (Test Failure):** The `test_google_search_tool_missing_api_key` test, which checks this error, started failing because the assertion was either too generic or expected the old message, and `ToolError.__cause__` was `None`.
    *   **Diagnosis 5b:** `fastmcp.ToolError` does not seem to populate `__cause__`. However, `fastmcp`'s own logger *does* log the underlying error message.
    *   **Solution 5c (Test Fix):** The test was modified to use `pytest`'s `caplog` fixture to capture logs from `FastMCP.fastmcp.tools.tool_manager` and assert that the specific, detailed error message for the missing API key was present in the logs.
    *   **Outcome 5c (Success):** All 30 tests passed again.

**Part 2: Troubleshooting `mcp-language-server` Symbol Resolution**

This became the most complex and time-consuming part of the session. The core problem was that the `mcp-language-server` (which uses `pyright-langserver` as its LSP backend for Python) could not find definitions for symbols, initially for the external `fastmcp` library and later even for project-local symbols.

1.  **Initial Problem:** `mcp-language-server`'s `definition` tool failed for `fastmcp.exceptions.ToolError`.
    *   **Attempt 1 (Dependency Declaration):** Checked `pyproject.toml`, found `fastmcp` was not listed. Used `uv pip list` to find the installed version (`2.6.1`) and added `fastmcp==2.6.1` to `[project.dependencies]`. Ran `uv pip install .`.
    *   **Outcome 1:** `definition` tool still failed after LS restart.
    *   **Attempt 2 (Pyright Configuration in `pyproject.toml`):** Added a `[tool.pyright]` section to `pyproject.toml` with `venvPath = "."`, `venv = ".venv"`, `pythonVersion = "3.11"`.
    *   **Outcome 2:** `definition` tool still failed after LS restart. User provided Pylance logs showing *VS Code's Pylance* was correctly configured and using the `.venv`. This was a key piece of information highlighting that the issue was likely with the `pyright-langserver` instance launched by `mcp-language-server`, not Pyright in general.
    *   **Attempt 3 (Correcting `pyright-langserver` Path):**
        *   Checked `mcp_settings.json`; `mcp-language-server` launched `pyright-langserver` by name (using `PATH`).
        *   Checked `.venv/bin`; `pyright-langserver` was *not* there.
        *   **Diagnosis:** `mcp-language-server` was using a global/different `pyright-langserver`.
        *   **Solution:** Ran `npm init -y` to create `package.json`, then `npm install pyright` to install it locally. Updated `mcp_settings.json` to use the absolute path `/Users/case/projects/serper-mcp/node_modules/.bin/pyright-langserver`.
    *   **Outcome 3:** `mcp-language-server` started crashing ("Connection closed"). `pyright-langserver` executable path was verified to be correct.
    *   **Attempt 4 (Ensuring Venv Activation for Spawned Process):** Added `VIRTUAL_ENV` environment variable to `mcp_settings.json` for the `mcp-language-server` process.
    *   **Outcome 4:** `definition` tool still failed for local and external symbols.
    *   **Attempt 5 (Verbose Logging & Log File Handling):**
        *   Enabled debug logging (`LOG_LEVEL`, `LOG_COMPONENT_LEVELS`) for `mcp-language-server` and redirected `stderr` (then `stdout & stderr`) to `mcp_language_server.log` using `bash -c` in `mcp_settings.json`.
        *   The log file became too large or was reported as binary, preventing `read_file`.
        *   Reduced `watcher` log verbosity.
        *   Log file was cleared.
        *   **Key Insight from (eventually read) Logs:** User provided logs showing Pyright was analyzing markdown files and many non-Python files, leading to excessive diagnostics.
    *   **Attempt 6 (Refining Pyright Scope - `pyproject.toml`):** Added `include = ["**/*.py"]` and `exclude = ["**/*.md"]` to `[tool.pyright]` in `pyproject.toml`.
    *   **Outcome 6:** `definition` tool still failed. The logs (when readable) indicated Pyright was *still* processing non-Python files. This meant Pyright was not respecting the `pyproject.toml` configuration.
    *   **Attempt 7 (Dedicated `pyrightconfig.json` - THE KEY SOLUTION):**
        *   Created a `pyrightconfig.json` file with `venvPath`, `venv`, `pythonVersion`, `include = ["**/*.py"]`, and `exclude = ["**/*.md", "package.json", "package-lock.json", "serper_mcp.egg-info/"]`.
        *   Removed the `[tool.pyright]` section from `pyproject.toml` to ensure `pyrightconfig.json` took precedence.
        *   Cleared the log file.
        *   **Simplified `mcp-language-server` command:** Reverted `mcp_settings.json` to directly call `mcp-language-server` (without `bash -c` and log redirection) as the log file was still problematic and the language server was crashing ("Not connected"). The `env` block with `VIRTUAL_ENV` (and temporarily removed logging vars) was kept.
    *   **Outcome 7 (SUCCESS!):** The `definition` tool successfully found the project-local symbol `serper_mcp_server.SerperApiClientError`. This confirmed that `pyrightconfig.json` was being correctly read and Pyright was now properly configured and analyzing only the relevant Python files within the correct virtual environment.

**Final Resolution:**

1.  **For `serper_mcp_server.py` and `serper_mcp_server_secure.py`:**
    *   The scripts were modified to default to `stdio` transport.
    *   `argparse` was added to allow transport selection via CLI argument (`--transport`), with precedence over the `MCP_SERVER_TRANSPORT` environment variable.
    *   The `mcp.run()` call was made conditional to only pass `host` and `port` for non-stdio transports.
    *   `print()` statements had `flush=True` added for better subprocess output.
    *   The "API key missing" error message was made more informative.
    *   These changes were validated by an expanded test suite.

2.  **For `mcp-language-server` symbol resolution:**
    *   `fastmcp==2.6.1` was added as an explicit dependency in `pyproject.toml`.
    *   `pyright` was installed locally into the project's `node_modules` using `npm` (after creating `package.json`).
    *   The `mcp_settings.json` configuration for `mcp-language-server` was updated to:
        *   Use the absolute path to the project-local `pyright-langserver` executable in `node_modules/.bin/`.
        *   Include the `VIRTUAL_ENV` environment variable pointing to the project's `.venv`.
        *   Crucially, Pyright's configuration (specifying `venvPath`, `venv`, `pythonVersion`, `include = ["**/*.py"]`, and `exclude` patterns for non-Python files like markdown and JSON) was moved from `pyproject.toml`'s `[tool.pyright]` section to a dedicated `pyrightconfig.json` file. This step was vital for ensuring Pyright correctly loaded and applied its configuration.
    *   The command for `mcp-language-server` in `mcp_settings.json` was reverted to a direct call (not via `bash -c` with log redirection) to ensure stability, as the redirection itself seemed to cause issues with the log file or server startup.

**Deeper Implications of the Final Resolution:**

1.  **Pyright Configuration Precedence/Reliability:** The troubleshooting highlighted that `pyright` (or at least the version/setup being used) might more reliably pick up its configuration from a dedicated `pyrightconfig.json` file than from a `[tool.pyright]` section in `pyproject.toml`, especially when launched as a subprocess by another tool like `mcp-language-server`. This is a critical takeaway for configuring Pyright in complex environments.
2.  **Language Server Environment Isolation:** When an external tool (like `mcp-language-server`) launches an LSP (like `pyright-langserver`), it's essential to ensure the LSP process:
    *   Is the correct, project-specific executable (e.g., from a local `node_modules` or project `.venv`).
    *   Inherits or is explicitly provided with all necessary environment variables (like `VIRTUAL_ENV`) to correctly locate and use the project's Python virtual environment and dependencies.
    *   Has its configuration (e.g., include/exclude patterns) correctly loaded.
3.  **Complexity of Bridging Tools:** The `mcp-language-server` acts as a bridge. Such bridges can introduce their own layer of complexity in terms of process management, environment variable propagation, and configuration loading for the tools they wrap. Debugging these requires looking at the bridge tool itself and the wrapped tool.
4.  **Importance of Granular Logging and Diagnostics:** The ability to enable verbose logging (even if temporarily problematic) and the specific error messages (like Pyright analyzing markdown) were crucial for pinpointing the issues. The initial lack of easily accessible, relevant logs from `mcp-language-server` significantly hampered the diagnosis.
5.  **Dependency Management:** Explicitly declaring dependencies (like `fastmcp` in `pyproject.toml` and `pyright` in `package.json`) is key for reproducible environments and for tools that rely on project metadata.
6.  **Iterative Troubleshooting:** This session demonstrated a classic iterative troubleshooting process: observe, hypothesize, test, refine. Many attempts were made, and each failure provided new information that guided subsequent steps.

The successful resolution means the user now has a correctly functioning `serper_mcp_server` and a `mcp-language-server` that can provide accurate code intelligence for their Python project, improving their development experience within the Roo Cline environment.

**Part 3: Further Probing of `mcp-language-server` (Post `pyrightconfig.json` Update)**

After the successful resolution of the primary symbol recognition issues by using `pyrightconfig.json`, further investigation into the `mcp-language-server`'s capabilities (still using `pyright-langserver` backend) yielded more nuanced insights, particularly regarding the `hover` and `definition` tools for dependency symbols.

1.  **`pyrightconfig.json` Enhancement:**
    *   The `pyrightconfig.json` file was updated to include an `executionEnvironments` array with a default environment for the project root (`.`).
    *   Within this environment, `extraPaths` was added to explicitly point to the virtual environment's `site-packages` directory (e.g., `.venv/lib/python3.11/site-packages`).
    *   **Purpose:** To provide Pyright with a more direct hint for locating installed dependencies, potentially aiding the `definition` tool.

2.  **Behavior of `definition` Tool (Post-Update):**
    *   **Test:** Attempted to get the definition of `fastmcp.FastMCP` using `symbolName: "fastmcp.FastMCP"`.
    *   **Outcome:** Still failed ("fastmcp.FastMCP not found"). The `extraPaths` modification did not enable the `definition` tool to resolve this dependency symbol by its fully qualified name.

3.  **Behavior of `hover` Tool (Post-Update & Further Probing):**
    *   **On `fastmcp.FastMCP` Instantiation (Re-verification):**
        *   Target: `FastMCP` in `mcp: FastMCP = FastMCP(...)` ([`serper_mcp_server.py:159`](serper_mcp_server.py:159)).
        *   **Outcome:** Consistently **successful**. Returned the full class signature for `FastMCP`. This confirms the language server *can* resolve and provide detailed info for this dependency symbol in this specific context, and the `pyrightconfig.json` changes didn't break this.
    *   **On Standard Library Import (`http.client`):**
        *   Target: `http.client` on import line ([`serper_mcp_server.py:2`](serper_mcp_server.py:2)).
        *   **Outcome:** Partially successful. Returned `(module) http`, indicating it resolved the top-level module but not the `client` submodule specifically in the hover response.
    *   **On Standard Library Class Usage (`http.client.HTTPSConnection`):**
        *   Target: `HTTPSConnection` in `conn = http.client.HTTPSConnection(host)` ([`serper_mcp_server.py:60`](serper_mcp_server.py:60)).
        *   **Outcome:** Partially successful. Returned `(module) client`, indicating it resolved the submodule containing the class, but not the `HTTPSConnection` class signature itself.
    *   **On Third-Party Class from `pydantic` (nested in `Annotated`):**
        *   Target: `Field` in `query: Annotated[str, Field(description="...")]` ([`serper_mcp_server.py:174`](serper_mcp_server.py:174)).
        *   **Outcome:** Failed ("No hover information available").

4.  **Conclusions from Further Probing:**
    *   **`hover` Tool Effectiveness is Context-Dependent:** The `hover` tool is most effective at providing detailed information (like class signatures) for dependency symbols when targeting their direct instantiation or usage (e.g., `FastMCP` in `mcp = FastMCP(...)`). Its ability to provide detailed information diminishes for symbols within complex qualified paths or nested within other constructs like `typing.Annotated`. For standard library components, it tended to provide module-level information rather than specific class/function signatures in the contexts tested.
    *   **`definition` Tool Limitations:** The `definition` tool (as used via `mcp-language-server` with only a `symbolName` parameter) remains unable to resolve dependency symbols by their fully qualified name, even with explicit `extraPaths` in `pyrightconfig.json`. This suggests the limitation might be inherent in how the `definition` tool queries Pyright or in Pyright's strategy for name-only lookups versus location-based lookups.
    *   **`pyrightconfig.json` Impact:** While the `extraPaths` addition was a logical step, it didn't resolve the `definition` tool's issues for dependency symbols. However, it also didn't negatively impact the previously working `hover` functionality. The core benefit of `pyrightconfig.json` (as established in Part 2) was ensuring Pyright correctly scoped its analysis to Python files within the specified virtual environment.

**Overall Language Server Status:**
The `mcp-language-server` can provide useful insights, particularly through the `hover` tool when applied to direct symbol usages. However, its capabilities for definition lookups of external dependencies by name alone are limited in this setup. The primary issue of parameter descriptions for the user's `serper_mcp_server.py` tools (which was the original trigger for some of this investigation) was resolved by code changes in that server file itself, not by language server adjustments.

Based on our extensive troubleshooting session with the `mcp-language-server` (which uses `pyright-langserver` as its backend), here are some suggestions on how its tool instructions and schema could be improved to guide users like me more effectively and potentially avoid errors or prolonged debugging:

1.  **For the `definition` Tool:**
    *   **Clarify `symbolName` Scope and Limitations:**
        *   **Current:** Takes `symbolName` (e.g., "mypackage.MyFunction").
        *   **Suggestion:** The instructions should explicitly state that while `symbolName` works reliably for symbols defined within the current project (e.g., "my_module.my_local_function"), its reliability for symbols imported from external dependencies (e.g., "installed_package.ClassName") is limited when only the name is provided.
    *   **Recommend `hover` as an Alternative for Dependencies:**
        *   **Suggestion:** Add a note: "If `definition` fails to find a symbol from an external library, try using the `hover` tool at a specific usage location (file, line, column) of that symbol, as this often provides more context for the language server."
    *   **Consider Optional Location Parameters (Enhancement):**
        *   **Suggestion (for the tool implementer):** If `pyright-langserver`'s "go to definition" capability can be enhanced by providing the location of the symbol's usage (like `hover` does), consider adding optional `filePath`, `line`, and `column` parameters to the `definition` tool. The instructions would then state: "For improved accuracy with external library symbols, providing `filePath`, `line`, and `column` where the symbol is used, in addition to `symbolName`, is recommended."
    *   **Provide Clear Examples for `symbolName`:**
        *   **Suggestion:** Include examples like:
            *   `"my_project_module.MyClass"`
            *   `"my_project_module.my_function"`
            *   `"installed_library.some_module.SomeClass"` (with a caveat about reliability if location isn't provided).

2.  **For the `hover` Tool:**
    *   **Set Expectations on Return Value Consistency:**
        *   **Suggestion:** The instructions should state: "The detail level of hover information can vary. For direct instantiations or calls (e.g., `MyClass()`), you may receive a full signature. For symbols within qualified paths (e.g., `module.submodule.symbol`) or nested constructs (e.g., inside `Annotated`), you might receive module information or less specific details. Hovering on import lines may also yield general module information rather than specific symbol details."
    *   **Highlight Best Practice for Dependencies:**
        *   **Suggestion:** "To get the most detailed hover information for a class or function from an external library, target a line where it is directly instantiated or called."

3.  **General Instructions for the `mcp-language-server`:**
    *   **Emphasize Correct Pyright Setup:**
        *   **Suggestion:** Add a "Prerequisites" or "Troubleshooting" section to the server's main instructions:
            *   "This server relies on a correctly configured `pyright-langserver`."
            *   "Ensure a `pyrightconfig.json` file (or `[tool.pyright]` in `pyproject.toml`) is present in your workspace root."
            *   "This configuration file **must** correctly specify the path to your Python virtual environment (e.g., using `venvPath` and `venv`) where your project dependencies are installed."
            *   "Use `include` and `exclude` patterns in your Pyright configuration to scope analysis to relevant Python files and avoid analyzing irrelevant files (like markdown or large data files) or directories (like `node_modules`)."
            *   "It is highly recommended to have `pyright-langserver` installed within your project's Node.js environment (`npm install pyright`) and to configure this MCP server to use that specific executable, rather than relying on a global installation."
    *   **Mention Log Files (If Applicable):**
        *   **Suggestion:** "If the server supports logging (e.g., to `mcp_language_server.log`), consult this file for diagnostic information from `pyright-langserver` if you encounter issues." (Though in our case it was empty, it's good general advice).

4.  **Error Message Passthrough (Enhancement):**
    *   **Suggestion (for the tool implementer):** If `pyright-langserver` returns more specific error details when a symbol isn't found (beyond a simple boolean failure), the `mcp-language-server` could attempt to pass these more granular error messages back to the client. This would make debugging failures more direct. For example, instead of just "symbol not found," something like "module 'X' not found in search paths" or "symbol 'Y' not found in module 'X'" would be more helpful.

By making these adjustments, the instructions would better prepare users (like me) for the nuances of interacting with `pyright-langserver` through the `mcp-language-server`, especially concerning dependency symbol resolution, and could lead to quicker and more successful outcomes.

Here are improved instructions for the `mcp-language-server` tools, based on observed capabilities:

---

**MCP Language Server: Tool Instructions**

This server provides language intelligence features for Python codebases, powered by `pyright-langserver`. For optimal performance, ensure your project includes a `pyrightconfig.json` file correctly configured for your Python virtual environment and project structure, specifying includes/excludes for analysis.

**Available Tools:**

**1. `definition`**
*   **Description:** Attempts to locate and return the source code definition of a symbol (function, class, variable, etc.).
*   **Effectiveness:** This tool is most effective for retrieving definitions of symbols that are defined within your current project workspace.
*   **Input Schema:**
    *   `symbolName` (string, required): The fully qualified name of the symbol whose definition you want to find (e.g., `my_module.MyClass`, `my_module.my_function`).
*   **Usage Notes:**
    *   Provide the complete, fully qualified name of the symbol.
    *   For symbols defined directly within your project files, this tool can navigate to their definitions.

**2. `hover`**
*   **Description:** Provides information about the symbol at a specific cursor position in a file, such as its type, signature, and docstring (if available).
*   **Effectiveness:** This tool is highly effective for understanding symbols at their point of use.
*   **Input Schema:**
    *   `filePath` (string, required): The path to the file (relative to the workspace root).
    *   `line` (number, required): The 1-based line number of the symbol.
    *   `column` (number, required): The 1-based column number of the symbol.
*   **Usage Notes:**
    *   **For External Dependencies (e.g., installed libraries):** To get the most detailed information (like a full class signature), target a line where the class is directly instantiated (e.g., `my_var = ImportedClass()`) or a function/method is directly called.
    *   **For Local Symbols:** Provides information for symbols defined within your project.
    *   **Varying Detail Levels:**
        *   When hovering over symbols in qualified paths (e.g., `module.submodule.symbol`) or on import lines, the information returned might be about the module rather than the specific symbol.
        *   Hovering over symbols nested within complex type annotations (e.g., a type used inside `typing.Annotated`) may not always yield hover information.
    *   Ensure `filePath`, `line`, and `column` accurately point to the beginning of the symbol you are interested in.

**3. `diagnostics`**
*   **Description:** Retrieves diagnostic information (errors, warnings, hints) for a specific file, as identified by the language server.
*   **Input Schema:**
    *   `filePath` (string, required): The path to the file to get diagnostics for.
    *   `contextLines` (boolean, optional, default: `false`): Number of lines to include around each diagnostic.
    *   `showLineNumbers` (boolean, optional, default: `true`): If true, adds line numbers to the output.
*   **Usage Notes:**
    *   Useful for identifying potential issues in your code as detected by Pyright.

**4. `edit_file`**
*   **Description:** Applies multiple text edits to a single file. This is useful for making targeted, programmatic changes.
*   **Input Schema:**
    *   `filePath` (string, required): Path to the file to edit.
    *   `edits` (array, required): A list of edit objects, where each object specifies:
        *   `startLine` (number, required): 1-based start line to replace, inclusive.
        *   `endLine` (number, required): 1-based end line to replace, inclusive.
        *   `newText` (string, optional): The text to replace the specified lines with. If omitted or empty, the lines will be deleted.
*   **Usage Notes:**
    *   Ensure line numbers are accurate to avoid unintended modifications.

**5. `references`**
*   **Description:** Finds all usages and references of a symbol throughout the codebase.
*   **Input Schema:**
    *   `symbolName` (string, required): The fully qualified name of the symbol to search for (e.g., `my_module.MyClass`).
*   **Usage Notes:**
    *   This tool helps in understanding where a particular symbol is used, which is valuable for refactoring or impact analysis. The effectiveness for dependency symbols may vary.

**6. `rename_symbol`**
*   **Description:** Renames a symbol at a specified position and updates all its references throughout the codebase.
*   **Input Schema:**
    *   `filePath` (string, required): The path to the file containing the symbol to rename.
    *   `line` (number, required): The 1-based line number where the symbol is located.
    *   `column` (number, required): The 1-based column number where the symbol is located.
    *   `newName` (string, required): The new name for the symbol.
*   **Usage Notes:**
    *   A powerful tool for refactoring. Ensure the location accurately points to the symbol you intend to rename.

---