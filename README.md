# hubCUBE

CUBE Hub and SingleRoleCUBE template collection for modular observation architecture

## 設計哲学（v4+ 物理シミュレーションフレームワーク）

**最大の改善点**

- 「更新するクラス」をなくす
- **Force Generator**（力を返すモジュール）と **Constraint**（拘束を返すモジュール）に徹底分解
- 状態更新は **Dynamics Solver** のみが担当

これにより、Bubble・Repair・Waypoint・Phase・LLM までを同じ力学フレームワーク上で自然に扱えるようになります。

### 推奨アーキテクチャ

```
Reality
   ↓
Sensors (Raw Observation)
   ↓
Observation / Interpreter
   ↓
PhaseState
   (position, velocity, energy, residue, confidence, entropy ...)
   ↓
Force Modules          Constraint Modules
   CarryForce           GeometryConstraint
   BubbleForce          BoundaryConstraint
   RepairForce          TopologyConstraint
   NoiseForce           ...
   GravityForce
   ↓
Dynamics Solver  (唯一状態を更新する場所)
   ↓
New PhaseState
   ↓
Evaluator / PhasePacket
   ↓
LLM / Action
```

### Force vs Constraint の区別

- **Force**（力を生成）: Carry, Bubble, Repair, Momentum, Noise, Gravity など
  → 「状態をどの方向に動かすか」を返す
- **Constraint**（拘束）: Geometry, Boundary, Topology など
  → 「状態をどの範囲に収めるか」を返す

### Carryの現在形（v4）

Carryは完全に **Force Generator** になりました。

- `compute_force(old_residue, persistence)` → carry_force のみを返す
- 状態更新は一切しない
- Dynamics Solver が他のForceと合成して新状態を計算

Residueは「状態」ではなく、PhaseStateの一部分として扱う方が自然です。

## Modules

- `CarryForce_v4.py` — Pure Carry Force Generator（力を返すだけ）
- `SimpleDynamicsSolver_example.py` — Force合成と状態更新の分離を示す例
- `CarryField_v3_Minimal.py` — v3版の参考用（現在は v4 推奨）
- `hubCUBE_SingleRole_Template*.py` — SingleRoleCUBEテンプレート
- `phase_shift_observer/` `grid_space_observer/` `phase_transition_observer/` — 各種観測モジュール

## Usage (CarryForce v4 + Solver pattern)

```python
from CarryForce_v4 import CarryForce
import torch

carry = CarryForce(default_persistence=0.87)
old_res = torch.randn(6) * 0.5

carry_force = carry.compute_force(old_res, persistence=0.90)

# 他のForceを合成する例
other_forces = torch.randn(6) * 0.12   # GeometryForceやMomentumForceの代わり

new_res = carry_force + other_forces
new_res = torch.clamp(new_res, -3.0, 3.0)  # BoundaryConstraint代行

pers = carry.compute_persistence(old_res, new_res)
print(f"Persistence: {pers:.4f}")
```

実験は忠実に実際行って、設計は物理シミュレーションとして清晰に。