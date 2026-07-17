# hubCUBE

**Phase Dynamics Engine for Modular Observation Architecture**

hubCUBE is a phase dynamics engine that treats information flow, uncertainty, repair, and adaptation as physical dynamical processes.

The LLM is **not** the owner of state. It is one reasoning component that interacts via structured PhasePacket.

## Quick Links

- **Full Architecture Vision**: [ARCHITECTURE.md](ARCHITECTURE.md)
- Latest Template: `hubCUBE_SingleRole_Template_v4_ForceBased.py`
- Core Force Module: `CarryForce_v4.py`

## Core Idea

```
Reality → Observation → Phase State → Forces + Constraints → Dynamics Solver → New State → LLM
```

State lives in hubCUBE. The LLM only receives local structured packets.

## Current Modules

- `CarryForce_v4.py` — Pure information propagation force
- `hubCUBE_SingleRole_Template_v4_ForceBased.py` — Recommended base template
- Various observers in `phase_shift_observer/`, `grid_space_observer/`, etc.

## Design Rules (Summary)

- Sensors measure, do not judge
- Forces influence, do not update state
- Only Dynamics Solver updates Phase State
- External systems (LLM etc.) interact only through PhasePacket

For the complete philosophy, principles, target architecture, and long-term goals, please read **[ARCHITECTURE.md](ARCHITECTURE.md)**.

実験は忠実に実際行って。