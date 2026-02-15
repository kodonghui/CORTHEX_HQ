---
name: pensieve
description: Load this skill immediately when the user expresses any intent. System capabilities (tools/knowledge/scripts) live inside the plugin and are maintained through plugin updates. User data must live at project-level `.claude/pensieve/` and is never overwritten by the plugin. When the user asks to improve Pensieve system behavior (plugin content), you must use the Self-Improve tool (`tools/self-improve/_self-improve.md`).
---

# Pensieve

Route user intent to the right tool/pipeline.

## Design conventions

- **System capability (updated via plugin)**: inside `skills/pensieve/`
  - tools / scripts / system knowledge / format READMEs
  - **No built‑in pipelines / maxims content**
- **User data (project-level, never overwritten)**: `.claude/pensieve/`
  - `maxims/`: your team principles (one maxim per file)
  - `decisions/`: project decision records
  - `knowledge/`: external references you add
  - `pipelines/`: project pipelines (seeded on install)
  - `loop/`: loop run outputs (one dir per loop)

## Built-in Tools (5)

### 1) Loop Tool

**When to use**:
- The task is complex and needs split + auto‑loop execution

**Entry**:
- Command: `commands/loop.md`
- Tool file: `tools/loop/_loop.md`

**Triggers**:
- `loop` / "use loop"

### 2) Self‑Improve Tool

**When to use**:
- User asks to improve Pensieve (pipelines/scripts/rules/behavior)
- After a loop ends for feedback & improvement

**Entry**:
- Command: `commands/selfimprove.md`
- Tool file: `tools/self-improve/_self-improve.md`

**Triggers**:
- "self‑improve" / "improve Pensieve"

### 3) Pipeline Tool

**When to use**:
- User wants to list pipelines for the current project

**Entry**:
- Command: `commands/pipeline.md`
- Tool file: `tools/pipeline/_pipeline.md`

**Triggers**:
- "pipeline" / "use pipeline"

### 4) Doctor Tool

**When to use**:
- Mandatory post-upgrade validation (structure/format compliance)
- Optional post-install health check
- User asks to validate user-data quality

**Entry**:
- Command: `commands/doctor.md`
- Tool file: `tools/doctor/_doctor.md`

**Triggers**:
- "doctor" / "health check" / "format check" / "migration check"

### 5) Upgrade Tool

**When to use**:
- User needs to migrate legacy data into `.claude/pensieve/`
- User asks for the ideal user-data structure

**Entry**:
- Command: `commands/upgrade.md`
- Tool file: `tools/upgrade/_upgrade.md`

**Triggers**:
- "upgrade" / "migrate user data"

---

SessionStart injects the **system capability path** and **project user‑data path** into context as the single source of truth at runtime.
