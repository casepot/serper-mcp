Okay, I understand. I will now generate the detailed, step-by-step implementation plan for the Rust-based MCP Language Server. This plan will incorporate the verified design decisions, link to relevant resources, outline checkpoints and testing goals, and identify areas for further research.

---

## Implementation Plan: Next-Generation MCP Language Server (Rust)

**Project Goal:** To create a high-performance, reliable, extensible, and LLM-friendly MCP Language Server in Rust, replacing and significantly improving upon the existing system.

**Core Technologies:** Rust, Tokio, `tower-lsp`, `tower`, `serde`, `lsp-types`, and specialized parsers for project configuration files.

**Guiding Principles:** Modularity, "it just works" reliability, superior diagnosability, performance, robustness, streamlined extensibility, optimized LLM agent experience, maintainability.

---

### Phase 0: Project Setup & Foundational Structures

**Objective:** Establish the project structure, core dependencies, and basic types for MCP communication.

**Tasks:**

1.  **Initialize Rust Project:**
    *   Action: `cargo new mcp_language_server_rs --lib` (or `--bin` if a thin binary wrapper is preferred initially, with core logic in a library).
    *   Rationale: Standard Rust project setup.
2.  **Add Core Dependencies to `Cargo.toml`:**
    *   `tokio = { version = "1", features = ["full"] }` ([Source: Tokio Docs](https://tokio.rs/tokio/tutorial/setup))
    *   `tower-lsp = "0.20"` ([Source: crates.io](https://crates.io/crates/tower-lsp)) - *Verify latest stable version.*
    *   `lsp-types = "0.95"` ([Source: crates.io](https://crates.io/crates/lsp-types)) - *Verify latest stable version compatible with `tower-lsp`.*
    *   `serde = { version = "1.0", features = ["derive"] }` ([Source: Serde Docs](https://serde.rs/))
    *   `serde_json = "1.0"` ([Source: crates.io](https://crates.io/crates/serde_json))
    *   `thiserror = "1.0"` ([Source: crates.io](https://crates.io/crates/thiserror))
    *   `anyhow = "1.0"` ([Source: crates.io](https://crates.io/crates/anyhow))
    *   `tracing = "0.1"` ([Source: crates.io](https://crates.io/crates/tracing))
    *   `tracing-subscriber = { version = "0.3", features = ["env-filter"] }` ([Source: crates.io](https://crates.io/crates/tracing-subscriber))
    *   `figment = { version = "0.10", features = ["toml", "env"] }` (or `config-rs`) ([Source: crates.io](https://crates.io/crates/figment))
    *   `notify = "6.0"` ([Source: crates.io](https://crates.io/crates/notify)) - *Verify latest stable version.*
    *   `tokio-util = { version = "0.7", features = ["codec"] }` ([Source: crates.io](https://crates.io/crates/tokio-util))
    *   `tokio-serde = { version = "0.9", features = ["json"] }` ([Source: crates.io](https://crates.io/crates/tokio-serde)) - *Verify latest stable version.*
    *   `clap = { version = "4.0", features = ["derive"] }` (if CLI options are needed) ([Source: crates.io](https://crates.io/crates/clap))
3.  **Define Core MCP Message Structures:**
    *   Action: Create Rust structs/enums for `McpRequest`, `McpResponse`, and common MCP error types using `serde` for serialization.
    *   Example:
        ```rust
        // src/mcp_protocol.rs
        use serde::{Serialize, Deserialize};

        #[derive(Serialize, Deserialize, Debug)]
        pub enum McpToolName {
            Initialize,
            Definition,
            Hover,
            // ... other LSP-related tools
            DiagnoseSetup,
            GetServerLogs,
        }

        #[derive(Serialize, Deserialize, Debug)]
        pub struct McpRequest {
            pub tool_name: McpToolName,
            pub arguments: serde_json::Value, // Or more specific types per tool
            pub request_id: Option<String>, // For correlation if needed
        }

        #[derive(Serialize, Deserialize, Debug)]
        pub struct McpResponse {
            pub request_id: Option<String>,
            pub result: Result<serde_json::Value, McpError>,
        }

        #[derive(Serialize, Deserialize, Debug, thiserror::Error)]
        pub enum McpError {
            #[error("Tool not found: {0}")]
            ToolNotFound(String),
            #[error("Invalid arguments: {0}")]
            InvalidArguments(String),
            #[error("LSP error: {0}")]
            LspError(String), // Potentially more structured
            #[error("Internal server error: {0}")]
            InternalError(String),
        }
        ```
    *   Rationale: Establishes the basic communication contract for the MCP Gateway.
4.  **Setup Basic Logging/Tracing:**
    *   Action: Initialize `tracing_subscriber` in `main.rs` (if binary) or an example.
    *   Example: `tracing_subscriber::fmt::init();`
    *   Rationale: Essential for debugging from the outset.
5.  **Define Project Modules:**
    *   Action: Create initial module structure (e.g., `mcp_gateway`, `lsp_management`, `workspace`, `configuration`, `diagnostics`, `common_types`).
    *   Example:
        ```rust
        // src/lib.rs
        pub mod mcp_protocol;
        pub mod mcp_gateway;
        pub mod lsp_management;
        // ... etc.
        ```
    *   Rationale: Organizes code logically from the start.

**Checkpoints & Testing Goals (Phase 0):**

*   Project compiles with all core dependencies.
*   Basic `McpRequest` and `McpResponse` can be serialized to and deserialized from JSON.
*   Logging is functional.

---

### Phase 1: MCP Gateway Implementation

**Objective:** Implement the MCP Gateway to handle incoming MCP connections (stdio initially), parse requests, and dispatch them (stubbed initially).

**Tasks:**

1.  **Implement Stdio Transport Handler:**
    *   Action: Using `tokio::io::stdin`, `tokio::io::stdout`, `tokio_util::codec::LengthDelimitedCodec`, and `tokio_serde::Framed`, create a loop that reads length-prefixed JSON messages, deserializes them into `McpRequest`, and (for now) logs them.
    *   Resource: Tokio tutorial on framing ([`tokio.rs/tokio/tutorial/framing`](https://tokio.rs/tokio/tutorial/framing)), `tokio-serde` docs ([`docs.rs/tokio-serde`](https://docs.rs/tokio-serde)).
    *   Example (conceptual):
        ```rust
        // src/mcp_gateway/stdio_transport.rs
        use tokio::io::{stdin, stdout, AsyncRead, AsyncWrite};
        use tokio_util::codec::{Framed, LengthDelimitedCodec};
        use tokio_serde::formats::Json;
        use futures::{StreamExt, SinkExt};
        use crate::mcp_protocol::{McpRequest, McpResponse};

        pub async fn run_stdio_gateway<S>(mut service: S) -> anyhow::Result<()>
        where
            S: tower::Service<McpRequest, Response = McpResponse, Error = anyhow::Error> + Send + 'static,
            S::Future: Send,
        {
            let stdin = stdin();
            let stdout = stdout();

            let length_delimited = Framed::new(stdin, LengthDelimitedCodec::new());
            let mut framed_stdin: tokio_serde::Framed<_, McpRequest, (), Json<McpRequest, ()>> =
                tokio_serde::Framed::new(length_delimited, Json::default());

            let mut framed_stdout = tokio_serde::Framed::new(
                Framed::new(stdout, LengthDelimitedCodec::new()),
                Json::<(), McpResponse>::default()
            );

            while let Some(request_result) = framed_stdin.next().await {
                match request_result {
                    Ok(request) => {
                        tracing::info!("Received MCP Request: {:?}", request);
                        // Later: Call the service
                        // let response = service.call(request).await?;
                        // framed_stdout.send(response).await?;
                        // For now, just echo a dummy response or log
                        let dummy_response = McpResponse {
                            request_id: request.request_id.clone(),
                            result: Ok(serde_json::json!({"status": "received"})),
                        };
                        if let Err(e) = framed_stdout.send(dummy_response).await {
                            tracing::error!("Failed to send MCP response: {}", e);
                        }
                    }
                    Err(e) => {
                        tracing::error!("Failed to deserialize MCP request: {}", e);
                        // Potentially send an McpError response
                    }
                }
            }
            Ok(())
        }
        ```
    *   Rationale: Establishes the primary communication channel with LLM agents.
2.  **Implement Basic Request Router/Orchestrator (Stubbed):**
    *   Action: Create a simple function or struct that takes an `McpRequest` and, based on `tool_name`, logs which service *would* be called.
    *   Rationale: Sets up the dispatch logic.
3.  **Integrate Router with Stdio Transport:**
    *   Action: The stdio handler now passes the deserialized `McpRequest` to the stubbed router.
    *   Rationale: Connects transport to initial logic.

**Checkpoints & Testing Goals (Phase 1):**

*   Server can receive a JSON `McpRequest` over stdio, deserialize it correctly.
*   Server can serialize a JSON `McpResponse` and send it back over stdio.
*   Basic end-to-end test: send a request via a simple client script (Python or Node.js) and verify a dummy response.
*   Router correctly identifies different `tool_name`s.

---

### Phase 2: LSP Management Service & `tower-lsp` Integration (Core)

**Objective:** Implement the core LSP interaction logic using `tower-lsp` for a single, simple LSP backend (e.g., a basic JSON or TOML language server if available, or `pyright-langserver` with minimal setup).

**Tasks:**

1.  **Define the `LspAdapter` Trait (Conceptual):**
    *   Action: While `tower-lsp` provides `LanguageServer`, we might want our own internal trait if we need to abstract over different `tower-lsp` instances or add custom management methods. For now, we'll directly implement `tower_lsp::LanguageServer`.
2.  **Implement a Basic `LanguageServer` (e.g., `PyrightAdapter`):**
    *   Action: Create a struct (e.g., `PyrightAdapter`) that implements `tower_lsp::LanguageServer`.
    *   Start with `initialize`, `initialized`, `shutdown`.
    *   Store the `tower_lsp::Client` provided by `LspService::new`.
    *   Resource: `tower-lsp` "Basic Language Server" example ([DeepWiki result](https://github.com/ebkalderon/tower-lsp/blob/master/examples/stdio.rs)).
    *   Example:
        ```rust
        // src/lsp_management/adapters/pyright_adapter.rs
        use tower_lsp::lsp_types::*;
        use tower_lsp::{LanguageServer, Client, LspService, Server}; // LspService & Server not used here directly

        #[derive(Debug)]
        pub struct PyrightAdapter {
            client: Client,
            // Potentially state for this specific LSP instance
        }

        impl PyrightAdapter {
            pub fn new(client: Client) -> Self {
                Self { client }
            }
        }

        #[tower_lsp::async_trait]
        impl LanguageServer for PyrightAdapter {
            async fn initialize(&self, params: InitializeParams) -> tower_lsp::jsonrpc::Result<InitializeResult> {
                tracing::info!("PyrightAdapter: initialize: {:?}", params);
                // Forward to actual pyright-langserver, or respond with fixed capabilities for now
                Ok(InitializeResult {
                    capabilities: ServerCapabilities {
                        text_document_sync: Some(TextDocumentSyncCapability::Kind(TextDocumentSyncKind::FULL)),
                        hover_provider: Some(HoverProviderCapability::Simple(true)),
                        // ...
                        ..Default::default()
                    },
                    server_info: Some(ServerInfo {
                        name: "mcp-language-server-rs (pyright-adapter)".to_string(),
                        version: Some(env!("CARGO_PKG_VERSION").to_string()),
                    }),
                })
            }

            async fn initialized(&self, params: InitializedParams) {
                tracing::info!("PyrightAdapter: initialized: {:?}", params);
                self.client.log_message(MessageType::INFO, "PyrightAdapter initialized via MCP Server!").await;
            }

            async fn shutdown(&self) -> tower_lsp::jsonrpc::Result<()> {
                tracing::info!("PyrightAdapter: shutdown");
                Ok(())
            }

            // Implement other methods like hover, definition etc. later
            async fn hover(&self, params: HoverParams) -> tower_lsp::jsonrpc::Result<Option<Hover>> {
                tracing::info!("PyrightAdapter: hover: {:?}", params);
                // Later: forward to pyright-langserver
                Ok(Some(Hover {
                    contents: HoverContents::Scalar(MarkedString::String("Hover from PyrightAdapter!".to_string())),
                    range: None,
                }))
            }
        }
        ```
3.  **LSP Management Service - Process Spawning:**
    *   Action: Implement logic to spawn an LSP backend process (e.g., `pyright-langserver --stdio`) using `tokio::process::Command`.
    *   Capture its stdin/stdout.
    *   Resource: Tokio process documentation ([`tokio::process::Command`](https://docs.rs/tokio/latest/tokio/process/struct.Command.html)).
4.  **LSP Management Service - `tower-lsp` Server Integration:**
    *   Action: For each spawned LSP backend, create a `tower_lsp::LspService` with your adapter (e.g., `PyrightAdapter`) and a `tower_lsp::Server`. Connect this `Server` to the spawned LSP's stdin/stdout.
    *   This means our MCP server will *host* a `tower-lsp` client/server pair for *each* LSP backend it manages.
    *   Rationale: This is the core of bridging MCP to LSP.
5.  **Connect MCP Router to LSP Management Service:**
    *   Action: When the MCP Router receives an LSP-related MCP request (e.g., `McpRequest { tool_name: McpToolName::Hover, ... }`), it should:
        1.  Identify the target workspace/LSP instance (initially, assume one global instance).
        2.  Find the corresponding `PyrightAdapter`'s `Client` (or a way to send requests to its `LspService`).
        3.  Construct the appropriate `lsp_types` request (e.g., `HoverParams`).
        4.  Use the adapter's `Client.send_request::<request_type>(params)` to send the request *to the `tower-lsp` service that is talking to `pyright-langserver`*.
        5.  Receive the response from the adapter's `Client`, convert it to an `McpResponse`, and send it back through the MCP Gateway.
    *   *Further Research Needed:* The exact mechanism for the MCP Router to "call into" a specific `tower-lsp` service instance needs refinement. It might involve:
        *   The LSP Management Service exposing a `tower::Service` interface itself for each managed LSP.
        *   Using channels to send requests to tasks managing each `tower-lsp` instance.
    *   *Dependency:* This step depends on a clear interface between the router and the LSP Management Service.

**Checkpoints & Testing Goals (Phase 2):**

*   `PyrightAdapter` can be initialized by a `tower-lsp` service.
*   LSP Management Service can spawn `pyright-langserver` (or a simpler LSP).
*   The `PyrightAdapter` (hosted by our MCP server) can successfully communicate (e.g., initialize) with the spawned `pyright-langserver`.
*   An MCP request for `hover` (sent to our MCP Gateway) can be routed through to the `PyrightAdapter`, which then (initially) returns a stubbed hover response.
*   **Key Test:** Send an MCP `hover` request, have it go through the MCP Gateway -> Router -> LSP Management Service -> `PyrightAdapter`, have the `PyrightAdapter` *actually* query the real `pyright-langserver` via its `tower-lsp::Client`, get a real hover response, and propagate it back as an `McpResponse`.

---

### Phase 3: Workspace & Configuration Services (Initial Implementation)

**Objective:** Implement basic workspace detection and configuration loading for one language (e.g., Python).

**Tasks:**

1.  **Workspace Service - Basic Structure:**
    *   Action: Define a struct to hold workspace information (e.g., root path). Implement basic file system watching for a given path using `notify`.
    *   Resource: `notify` crate documentation ([`docs.rs/notify`](https://docs.rs/notify)).
2.  **Configuration Service - Python Project Detection:**
    *   Action:
        *   Implement logic to detect a Python project (e.g., presence of `pyproject.toml`, `.python-version`, common Python file extensions).
        *   Parse `pyproject.toml` using the `pyproject-toml` crate ([`docs.rs/pyproject-toml`](https://docs.rs/pyproject-toml)). Extract basic info like project name, dependencies.
        *   Attempt to detect a virtual environment (check `VIRTUAL_ENV`, look for `.venv` folders).
    *   Resource: `pyproject-toml` docs. Stack Overflow for venv detection techniques.
3.  **Integration with LSP Management Service:**
    *   Action: The LSP Management Service should consult the Configuration Service when preparing to launch an LSP (e.g., `pyright-langserver`). The Configuration Service provides the detected Python interpreter path (from venv or system) and workspace root.
    *   Rationale: Decouples LSP launching from configuration discovery.

**Checkpoints & Testing Goals (Phase 3):**

*   Workspace Service can detect file changes in a monitored directory.
*   Configuration Service can parse a `pyproject.toml` and extract project name.
*   Configuration Service can identify a Python virtual environment if `VIRTUAL_ENV` is set or a `.venv` folder exists.
*   LSP Management Service uses information from Configuration Service to (attempt to) launch `pyright-langserver` with the correct interpreter.

---

### Phase 4: Expanding LSP Functionality & Adapters

**Objective:** Implement more LSP features in the `PyrightAdapter` and add a second adapter (e.g., `RustAnalyzerAdapter`).

**Tasks:**

1.  **Implement More `PyrightAdapter` Methods:**
    *   Action: Add handlers for `textDocument/definition`, `textDocument/completion`, `textDocument/publishDiagnostics` (receiving from LSP, forwarding to MCP client), etc.
    *   These methods will typically:
        1.  Receive `lsp_types` params from `tower-lsp`.
        2.  The adapter's `tower-lsp::Client` (which is connected to the *actual* `pyright-langserver`) is used to forward the request.
        3.  The response from `pyright-langserver` is returned.
2.  **Implement `RustAnalyzerAdapter`:**
    *   Action: Create a new adapter for `rust-analyzer`.
    *   Parse `Cargo.toml` using `cargo_toml` crate ([`docs.rs/cargo_toml`](https://docs.rs/cargo_toml)).
    *   Parse `rust-project.json` (if present) using `serde_json`.
    *   LSP Management Service needs to be able to launch `rust-analyzer`.
3.  **Refine LSP Management Service:**
    *   Action: Allow managing multiple types of LSP backends and multiple instances. This will likely involve a registry of available adapter types and active instances.
    *   The MCP Router needs to be ables to specify *which* LSP instance a request is for (e.g., based on file type or workspace).

**Checkpoints & Testing Goals (Phase 4):**

*   MCP requests for `definition`, `completion` for Python files work end-to-end via `PyrightAdapter`.
*   Diagnostics from `pyright-langserver` are received by `PyrightAdapter` and can be (conceptually) forwarded.
*   `RustAnalyzerAdapter` can be initialized and respond to basic requests for Rust projects.
*   The system can differentiate requests for Python vs. Rust files and route them to the correct adapter.

---

### Phase 5: Advanced Features & Polish

**Objective:** Implement advanced features from the PRD, improve diagnostics, and enhance robustness.

**Tasks:**

1.  **Implement `DiagnoseSetup` MCP Tool:**
    *   Action: This tool in the Diagnostics Aggregation Service will query the Configuration Service and LSP Management Service to report on detected project types, LSP configurations, and LSP process statuses.
2.  **Implement Other LLM-Centric MCP Tools:**
    *   Action: `getReferencesWithContext`, `getTypeHierarchy`, etc. These will involve orchestrating multiple calls to the relevant LSP adapters.
3.  **Robust Error Handling & Propagation:**
    *   Action: Ensure errors from LSP backends, adapters, and internal services are converted into meaningful `McpError` responses.
4.  **Configuration Overrides via MCP:**
    *   Action: Allow agents to provide/override LSP configurations.
5.  **Comprehensive Testing:**
    *   Unit tests for individual components/modules.
    *   Integration tests for MCP request flows through to LSP backends.
    *   Tests for various project configurations and LSP server behaviors.
    *   Stress tests for concurrency and resource management.
6.  **Documentation:**
    *   Internal architecture documentation.
    *   MCP API documentation for agent developers.
    *   User/Operator guide for running and configuring the server.

**Checkpoints & Testing Goals (Phase 5):**

*   `DiagnoseSetup` provides accurate and helpful information.
*   Advanced MCP tools function correctly.
*   The server is stable under load and handles LSP crashes gracefully.
*   Comprehensive test suite passes.
*   Documentation is complete.

---

### Further Research & Verification During Implementation:

*   **MCP Router to LSP Service Communication:** The precise mechanism for the MCP Router to dispatch requests to the correct, dynamically managed `tower-lsp` service instance (representing an LSP backend) needs detailed design. Options include:
    *   A `tower::Service` implementation for the LSP Management Service that can route based on an LSP identifier.
    *   Using `mpsc` channels to send requests to tasks that own each `tower-lsp` service instance.
*   **State Management in Adapters:** For complex LSPs or features, how best to manage state within an adapter (e.g., document caches) while ensuring thread safety with `tower-lsp`'s async request handling. `Arc<Mutex/RwLock<State>>` is common, but specific access patterns need care.
*   **Dynamic Capability Registration:** How to handle `client/registerCapability` requests from LSPs and reflect these changes in the MCP capabilities.
*   **Workspace Symbol Indexing/Caching:** If we implement a shared cache for symbols across LSPs or for faster workspace symbol searches, the design of this cache and its update strategy will need research.
*   **Security Considerations for LSP Processes:** Sandboxing or resource limiting for LSP backend processes if they handle untrusted code.

This implementation plan provides a structured approach. Each phase and task will involve iterative development and refinement. The key is to build a solid foundation in the early phases and then layer on more complex functionality.