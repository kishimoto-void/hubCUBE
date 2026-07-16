# hubCUBE

CUBE Hub and SingleRoleCUBE template collection for modular observation architecture

## Modules

- `hubCUBE_SingleRole_Template*.py` — SingleRoleCUBE のテンプレート（状態・役割分化・観測の最小構成）
  - `hubCUBE_SingleRole_Template_v2.2_ImprovedCarry.py` **NEW** — **residue carryメカニズムを大幅改良**
    - Adaptive Decay（coherence/entropy状態依存の保持率制御）
    - Momentum Carry（residue velocityの慣性項で滑らかなattractor形成）
    - Geometry Modulation（局所活性に基づくdelta強調）
    - Soft Clamp（tanhベースの滑らかな境界処理）
    - 新メトリクス: `carry_persistence`, `residue_velocity` で定量観測可能
    - 実験により静寂期のresidue持続性向上とダイナミクスの安定化を確認済み
- `CUBE_Anomaly_Detection_v*.py` — 異常検知・ロバスト化の実験モジュール群
- `phase_shift_observer/PhaseShiftObserverCUBE_v4_3.py` — **位相ズレ・同期トポロジー観測器**（Ver.4.3）
  - 高階時間力学（drift / acceleration / jerk）
  - リングトポロジー対応の propagation_trend（torch.roll 使用）
  - 動的リンク追跡：Coherence + Phase Lag + Stable Duration（link_durations テンソルで長期同調を追跡）
  - external_phases による hubCUBE 実ノード位相注入対応
  - デバイス自動同期（CPU/GPU）
  - 完全シリアライズ対応（to_dict / from_dict）
- `grid_space_observer/GridSpaceObserver_v4_2.py` — **時空間幾何・流動解析観測器**（Ver.4.2）
  - 幾何変形（主軸半径・縮退度・曲率） / 時間自己相関・BPMスペクトル / 空間密度エントロピー・流動マトリクスを統合解析
  - 3軸偏差指数の tanh ソフトクリップ + 慣性平滑化
  - アトラクタ寿命（norm_attractor_age）の正規化出力
  - アスキー・フローマトリクス可視化レンダラー搭載（render_flow_matrix）
  - SingleRoleCUBE 基底を継承したモジュラー設計
- `phase_transition_observer/PhaseTransitionCUBE_v1.2_LinkDynamics.py` — **リンク力学観測器**（Ver.1.2）
  - **Link Aging + Plasticity**：リンクに寿命・使用履歴を持たせ、過去によく共鳴した結合が再び強くなりやすい
  - **Flow**：各リンクを通る情報流（Δresidue × strength）を記録し、構造と動態を分離して観測
  - **Network Metrics**：`active_links`、`avg_strength`、`network_flux`、`total_flux` を第一級の観測対象に
  - Linkを単なる可視化ではなく、実際のcoupling力として residue更新に反映（動的Jij）
  - CUBEらしい「Linkが世界を形成する」閉ループ力学の基盤を構築

## Usage Example (Improved Carry v2.2)

```python
from hubCUBE_SingleRole_Template_v2.2_ImprovedCarry import SingleRoleCUBE, CUBEHub, ResidueObserverCUBE
import torch

hub = CUBEHub("CarryTestHub")
res_cube = ResidueObserverCUBE(carry_momentum=0.25, adaptive_strength=0.30)
hub.register(res_cube)

for i in range(8):
    x = torch.tensor([0.7 + 0.3 * (i % 3 - 1)])
    results = hub.observe_all(x)
    m = results["ResidueObserver"]
    print(f"Step {i+1}: res={m.residue_norm:.4f} carry_pers={m.carry_persistence:.3f} vel={m.residue_velocity:.4f}")
```

実験は忠実に実際行って。