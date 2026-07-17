# hubCUBE

**Phase Dynamics Engine for Modular Observation Architecture**

hubCUBE is a phase dynamics engine that treats information flow, uncertainty, repair, and adaptation as physical dynamical processes.

The LLM is **not** the owner of state. It is one reasoning component that interacts via structured commands through the Kernel.

## Quick Links

- **Full Architecture Vision**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Reorganization Log**: [REORGANIZATION_LOG.md](REORGANIZATION_LOG.md)
- **Latest Kernel**: `hubCUBE_Kernel_v2.1_RC.py` — External command integration, Validator, Ingress, Audit & Snapshot (2026-07-17 added)
- **Physics Kernel (bubbleParticle)**: [hubCUBE_PhaseSnapshot_BubbleKernel_v3.py](hubCUBE_PhaseSnapshot_BubbleKernel_v3.py) — Pure deterministic state transition kernel (2026-07-17 added)
- Latest Template: `templates/hubCUBE_SingleRole_Template_v4_ForceBased.py`
- Core Force Module: `forces/CarryForce_v4.py`

## Core Idea

```
Reality → Observation → Phase State → Forces + Constraints → Dynamics Solver → New State → LLM (via Kernel)
```

State lives in hubCUBE. The LLM only interacts through the validated Kernel ingress.

## Physics Kernel: bubbleParticle

**bubbleParticle** は hubCUBE のために設計された**純粋な状態遷移カーネル**です。

本カーネルは感情・意味・LLM固有の概念を一切持ちません。
扱うのは以下の要素のみです：

- Position / Velocity / Acceleration
- ForceModel (≬ Protocol)
- ConstraintModel (≬ Protocol)
- PhaseSnapshot (完全イミュータブル)
- RK4DynamicsSolver (=)
- PureNumericalEvaluator (≠)

意味論・感情・記憶・認知はすべて上位レイヤーである **hubCUBE** が担当し、
bubbleParticle は数理的・幾何学的な状態遷移のみを提供します。

### 役割分担

```
Meaning / Emotion / Memory / Cognition
         ↓
      hubCUBE
         ↓
  bubbleParticle  (Physics Kernel)
         ↓
      Mathematics / Geometry / Time Integration
```

この分離により、物理カーネルを変更することなく、異なる認知モデルや観測アーキテクチャへ適用可能になります。

- Dedicated repository: https://github.com/kishimoto-void/bubbleparticle
- README（役割定義）: https://github.com/kishimoto-void/bubbleparticle/blob/main/README.md

## Current Modules (after 2026-07-17 update)

- `hubCUBE_PhaseSnapshot_BubbleKernel_v3.py` — **New** Pure physics state transition kernel with immutable PhaseSnapshot, ≌ protocols, and separated evaluation layer
- `hubCUBE_Kernel_v2.1_RC.py` — OS Kernel for safe external intervention handling
- `forces/CarryForce_v4.py` — Pure information propagation force（最新推奨）
- `templates/hubCUBE_SingleRole_Template_v4_ForceBased.py` — Recommended base template（最新推奨）
- `experiments/` — Validation experiments, legacy versions
- Various observers in `phase_shift_observer/`, `grid_space_observer/`, `phase_transition_observer/`

## Design Rules (Summary)

- Sensors measure, do not judge
- Forces influence, do not update state
- Only Dynamics Solver updates Phase State
- **External systems (LLM etc.) interact only through the Kernel** with strict validation
- **Physics layer is delegated to bubbleParticle** for clean separation of concerns

**Note**: 2026-07-17 に PhaseSnapshot BubbleKernel v3 を追加。詳細は [hubCUBE_PhaseSnapshot_BubbleKernel_v3.py](hubCUBE_PhaseSnapshot_BubbleKernel_v3.py) を参照。

For the complete philosophy, principles, target architecture, and long-term goals, please read **[ARCHITECTURE.md](ARCHITECTURE.md)**.

実験は忠実に実際行って。