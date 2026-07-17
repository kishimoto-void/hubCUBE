# hubCUBE

**Phase Dynamics Engine for Modular Observation Architecture**

hubCUBE is a phase dynamics engine that treats information flow, uncertainty, repair, and adaptation as physical dynamical processes.

The LLM is **not** the owner of state. It is one reasoning component that interacts via structured PhasePacket.

## Quick Links

- **Full Architecture Vision**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Reorganization Log**: [REORGANIZATION_LOG.md](REORGANIZATION_LOG.md)
- Latest Template: `templates/hubCUBE_SingleRole_Template_v4_ForceBased.py`
- Core Force Module: `forces/CarryForce_v4.py`

## Core Idea

```
Reality → Observation → Phase State → Forces + Constraints → Dynamics Solver → New State → LLM
```

State lives in hubCUBE. The LLM only receives local structured packets.

## Current Modules (after 2026-07-17 reorganization)

- `forces/CarryForce_v4.py` — Pure information propagation force（最新推奨）
- `templates/hubCUBE_SingleRole_Template_v4_ForceBased.py` — Recommended base template（最新推奨）
- `experiments/` — Legacy versions, Anomaly Detection experiments, examples
- Various observers in `phase_shift_observer/`, `grid_space_observer/`, `phase_transition_observer/`

## Design Rules (Summary)

- Sensors measure, do not judge
- Forces influence, do not update state
- Only Dynamics Solver updates Phase State
- External systems (LLM etc.) interact only through PhasePacket

**Note**: 2026-07-17 にルートレベルのバージョン混在を解消する整理を実施しました。詳細は [REORGANIZATION_LOG.md](REORGANIZATION_LOG.md) をご覧ください。

For the complete philosophy, principles, target architecture, and long-term goals, please read **[ARCHITECTURE.md](ARCHITECTURE.md)**.

実験は忠実に実際行って。