# hubCUBE

**Phase Dynamics Engine for Modular Observation Architecture**

hubCUBE is a phase dynamics engine that treats information flow, uncertainty, repair, and adaptation as physical dynamical processes.

The LLM is **not** the owner of state. It is one reasoning component that interacts via structured commands through the Kernel.

## Quick Links

- **Full Architecture Vision**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Reorganization Log**: [REORGANIZATION_LOG.md](REORGANIZATION_LOG.md)
- **Latest Kernel**: `hubCUBE_Kernel_v2.1_RC.py` — External command integration, Validator, Ingress, Audit & Snapshot (2026-07-17 added)
- Latest Template: `templates/hubCUBE_SingleRole_Template_v4_ForceBased.py`
- Core Force Module: `forces/CarryForce_v4.py`

## Core Idea

```
Reality → Observation → Phase State → Forces + Constraints → Dynamics Solver → New State → LLM (via Kernel)
```

State lives in hubCUBE. The LLM only interacts through the validated Kernel ingress.

## Current Modules (after 2026-07-17 update)

- `hubCUBE_Kernel_v2.1_RC.py` — **New** OS Kernel for safe external intervention handling
- `forces/CarryForce_v4.py` — Pure information propagation force（最新推奨）
- `templates/hubCUBE_SingleRole_Template_v4_ForceBased.py` — Recommended base template（最新推奨）
- `experiments/` — Validation experiments, legacy versions
- Various observers in `phase_shift_observer/`, `grid_space_observer/`, `phase_transition_observer/`

## Design Rules (Summary)

- Sensors measure, do not judge
- Forces influence, do not update state
- Only Dynamics Solver updates Phase State
- **External systems (LLM etc.) interact only through the Kernel** with strict validation

**Note**: 2026-07-17 に Kernel v2.1 RC を追加。詳細は [hubCUBE_Kernel_v2.1_RC.py](hubCUBE_Kernel_v2.1_RC.py) を参照。

For the complete philosophy, principles, target architecture, and long-term goals, please read **[ARCHITECTURE.md](ARCHITECTURE.md)**.

実験は忠実に実際行って。