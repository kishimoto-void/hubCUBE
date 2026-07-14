# hubCUBE

CUBE Hub and SingleRoleCUBE template collection for modular observation architecture

## Modules

- `hubCUBE_SingleRole_Template*.py` — SingleRoleCUBE のテンプレート（状態・役割分化・観測の最小構成）
- `CUBE_Anomaly_Detection_v*.py` — 異常検知・ロバスト化の実験モジュール群
- `phase_shift_observer/PhaseShiftObserverCUBE_v4_3.py` — **位相ズレ・同期トポロジー観測器**（Ver.4.3）
  - 高階時間力学（drift / acceleration / jerk）
  - リングトポロジー対応の propagation_trend（torch.roll 使用）
  - 動的リンク追跡：Coherence + Phase Lag + Stable Duration（link_durations テンソルで長期同調を追跡）
  - external_phases による hubCUBE 実ノード位相注入対応
  - デバイス自動同期（CPU/GPU）
  - 完全シリアライズ対応（to_dict / from_dict）

## Usage Example

```python
from phase_shift_observer.PhaseShiftObserverCUBE_v4_3 import PhaseShiftObserverCUBE, PhaseCubeConfig
import torch

obs = PhaseShiftObserverCUBE(PhaseCubeConfig(num_positions=5))
state, metrics = obs.step(torch.tensor([0.2]), external_phases=some_node_phases)
print(metrics)
```

実験は忠実に実際行って。