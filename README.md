# hubCUBE

CUBE Hub and SingleRoleCUBE template collection for modular observation architecture

## 最新推奨（v4 ForceBased）

**`hubCUBE_SingleRole_Template_v4_ForceBased.py`** をご利用ください。

- CarryForce を内部で compose
- Force / Constraint 分離の思想を反映
- 状態更新の責務を明確に

詳細は `DESIGN.md` を参照。

## 設計哲学（v4+）

Force Generator と Constraint を分離し、Dynamics Solver のみが状態を更新する物理シミュレーションフレームワークを目指しています。

- CarryForce : 純粋に「運ぶ力」のみ生成
- 将来的に BubbleForce, RepairForce, GeometryConstraint などを追加可能

## Modules

### Core (v4)
- `CarryForce_v4.py` — Pure Carry Force Generator
- `SimpleDynamicsSolver_example.py` — Force 合成の最小例
- `hubCUBE_SingleRole_Template_v4_ForceBased.py` — **最新推奨テンプレート**
- `DESIGN.md` — アーキテクチャ設計書

### Previous iterations (参考)
- `hubCUBE_SingleRole_Template_v2.2_ImprovedCarry.py`
- `CarryField_v3_Minimal.py`

### Observers
- `phase_shift_observer/PhaseShiftObserverCUBE_v4_3.py`
- `grid_space_observer/GridSpaceObserver_v4_2.py`
- `phase_transition_observer/PhaseTransitionCUBE_v1.2_LinkDynamics.py`

## Quick Start

```python
from hubCUBE_SingleRole_Template_v4_ForceBased import SingleRoleCUBE, CUBEHub
import torch

hub = CUBEHub()
hub.register(SingleRoleCUBE(role_name="MyObserver", num_positions=6))

for step in range(5):
    x = torch.tensor([0.5 + 0.2 * step])
    metrics = hub.observe_all(x)
    print(metrics)
```

実験は忠実に実際行って。