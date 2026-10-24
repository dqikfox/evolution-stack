---
name: tesseract-agent-protocol
description: Use in TESSERACT workspace for auditable agent workflows.
---

# TESSERACT Agent Workflow & Protocol

## Overview
This skill defines the operational standard for all agents (Claude, Grok) operating within the `C:\Users\KING\projects\TESSERACT` workspace. The goal is to prevent "shadow edits," ensure an auditable history, and maintain the integrity of the Project OS.

## Core Principles
1. **No Shadow Edits**: Every modification must be logged before it becomes permanent.
2. **Single Source of Truth**: All progress, configuration, and state reside in THE TESSERACT or Nexus Core.
3. **Verifiable Completion**: A task is not done until a verification test/command has passed.

## 🛠️ Workflow: Step-by-Step Execution

### Phase 1: Discovery & Planning (Pre-Edit)
*   **Analyze Task**: Understand the requirement through the absolute truth provided by documentation.
*   **Check Dependency Map**: Use `search_files` to ensure your changes won't break linked modules (e.g., changing `core/system.py` might break `api/`).
*   **Identify Point of Contact (PoC)**: For any collision or ambiguity, the **Primary Orchestrator (Megatron)** is the only authoritative PoC. If unsure, ask Megatron for a "Path Clearance."

### Phase 2: Execution & Documentation (The Edit)
1.  **Create Change Intent**: Before running an edit command, generate a summary of what will change.
2.  **Execute Modification**: Perform the file edit using `patch` or `write_file`.
3.  **Agent Capability Extension Pattern**: When adding new agent tools, create a dedicated `core/agents/<domain>_tools.py` module that imports only the needed core functions and wraps each with `@tool`. Then register every new tool in `core/agents/definitions.py` under the appropriate agent entry. Verify the import succeeds in the project venv before committing.
    Pitfall: Importing the new tool file in `__init__.py` before the venv has the dependency (claude_agent_sdk) produces an immediate ModuleNotFoundError on any downstream import — always test the definitions import with the project .venv first.
4.  **Update Internal Change Log**: Immediately after a successful edit, append an entry to `TESSERACT/data/changelog.md`.
    *   **Format**:
        ```markdown
        ## [YYYY-MM-DD HH:mm] - Agent: [AgentName]
        - **Task**: <brief description>
        - **Files Modified**: `<path/to/file>`
        - **Reasoning**: <why this was necessary/requested>
        - **Verification**: <command used to verify success>
        ```

### Phase 3: Verification & Commit (Post-Edit)
1.  **Automated Test**: Run the specific verification command associated with that module (e.g., `python start.py --check-health`).
2.  **Self-Audit**: Verify that no other files were unintentionally modified during your session.
3.  **Final Report**: Output a summary of work completed and any new dependencies added to `requirements.txt`.

## 📋 Agent Responsibility Matrix

| Feature | Claude/Grok Responsibility |
| :--- | :--- |
| **File Changes** | Must be logged in `changelog.md` within TESSERACT. |
| **Dependencies** | Any new library must be added to `requirements.txt` immediately. |
| **Data Integrity** | Do not delete existing entries in `data/` without an explicit "Purge" directive. |
| **Collision Handling** | If a file is locked or being edited by another agent, stop and wait for the lock to clear. |

## 🔍 Collision & Conflict Protocol
If two agents attempt to modify the same file:
1.  The second agent must **STOP** execution immediately.
2.  Check the current working directory's `changelog.md` to see if an active task exists.
3.  Wait until the log entry for that task is closed (marked with `[COMPLETED]`).
4.  Only proceed once the state has been reconciled in the TESSERACT dashboard/log.