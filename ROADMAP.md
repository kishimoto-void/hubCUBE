# hubCUBE 開発・実験ロードマップ

**作成日**: 2026-07-17
**目的**: ARCHITECTURE.md / DESIGN.md で示された理想構造を実現するための、具体的なコード実験項目と優先順位を明確にする。

> 「実験は忠実に実際行って」

---

## 現在の状況（2026-07-17 整理後）

### 完了・安定している部分
- `forces/CarryForce_v4.py`：純粋なForce Generatorとして良好
- `templates/hubCUBE_SingleRole_Template_v4_ForceBased.py`：CarryForceをcomposeした最新テンプレート
- `experiments/SimpleDynamicsSolver_example.py`：最小Solverの考え方を示す
- ディレクトリ構造の基盤（forces/, templates/, experiments/）

### まだルートに残っているレガシー
- CUBE_Anomaly_Detection_v2.6〜2.8
- 旧SingleRole Template群（v2.1, v2.2 など）

### 大きなギャップ（Missing Pieces）
- **Constraints** 層が全く存在しない
- **Dynamics Solver** が本格的に実装されていない（Template内で簡易的に状態更新している）
- **追加のForce**（Bubble, Repair, Momentum, Noise など）が未実装
- **PhasePacket**（LLMとの構造化インターフェース）が未定義
- **Repair / Recovery** メカニズムが弱い
- **Evaluation層** が未整備
- Observers（grid_space, phase_shift など）が architecture のどの層に位置づくか未整理

---

## 優先順位付きロードマップ

### Phase 1: 基盤強化（即時〜1週間以内推奨）
**目標**: 「Force + Constraint + Solver」の最小ループを成立させる

| 優先 | 実験項目 | 提案ファイル | 内容・目的 | 難易度 |
|------|----------|--------------|------------|--------|
| 1 | GeometryConstraint / BoundaryConstraint | `constraints/GeometryConstraint.py` | 幾何的制約と境界制約の最小実装。状態を直接更新せず、許容範囲を返す | 中 |
| 2 | 最小 DynamicsSolver | `dynamics/MinimalDynamicsSolver.py` | CarryForce + Constraint を受け取り、新PhaseStateを返す唯一の更新担当 | 中 |
| 3 | PhasePacket 定義 | `packet/PhasePacket.py` | LLMが受け取る構造化データ（local state summary + metrics + suggestions） | 低 |
| 4 | 簡易 RepairForce 実験 | `forces/RepairForce_v1.py` | residueの欠損・異常を検知して修復方向の力を生成する実験 | 中 |

**推奨実験の進め方**:
1. `constraints/` ディレクトリ作成
2. `MinimalDynamicsSolver` で Template v4 をリファクタ（状態更新をSolverに移譲）
3. 小さな統合実験スクリプトを `experiments/force_constraint_integration.py` に作成

### Phase 2: Forceの拡充とObserver統合（1〜3週間）

| 優先 | 実験項目 | 提案ファイル | 内容・目的 | 難易度 |
|------|----------|--------------|------------|--------|
| 1 | BubbleForce | `forces/BubbleForce.py` | 非平衡感情・張力の局所的「泡」生成と伝播実験 | 中〜高 |
| 2 | MomentumForce | `forces/MomentumForce.py` | 慣性・運動量を考慮した力の生成 | 低〜中 |
| 3 | Observer統合 | `observers/` ディレクトリ + `__init__.py` | 既存の grid_space_observer / phase_shift_observer を architecture の Observation層に位置づけ | 中 |
| 4 | 複数Role間相互作用実験 | `experiments/multi_role_hub_test.py` | CUBEHubで複数のSingleRoleCUBEを登録し、相互のresidue影響を観測 | 中 |

### Phase 3: 評価・修復・長期記憶（中長期）

- Evaluation層の実装（リスク・重要度・修復優先度の定量化）
- Residueの長期持続・減衰パターンの系統的実験
- Repairメカニズムの本格化（欠損復元、phase bias修正）
- Phase Stateのよりリッチな表現（velocity, energy, waypoint など）
- 他のプロジェクト（VGE, wCUBE, EmotionalVoidCore）との接続実験

---

## 具体的なコード実験提案（すぐに始められるもの）

### 1. Force + Constraint 統合実験（最優先推奨）
**ファイル**: `experiments/force_constraint_minimal_loop.py`

目的:
- CarryForce で力を生成
- GeometryConstraint / BoundaryConstraint で制約を適用
- MinimalDynamicsSolver で状態を更新
- これを1ループで回して residue の挙動を定量観測

### 2. PhasePacket プロトタイプ
**ファイル**: `packet/PhasePacket.py` + `experiments/phase_packet_demo.py`

内容:
```python
@dataclass
class PhasePacket:
    role_name: str
    local_residue: torch.Tensor
    metrics: dict
    suggested_actions: list[str]
    confidence: float
```
LLMはこのパケットだけを見て次の仮説を立てる、という最小形を実験。

### 3. Residue Repair 実験
**ファイル**: `experiments/residue_repair_test.py`

- 意図的にresidueを欠損・ノイズ付与
- RepairForce（または簡易修復ロジック）でどの程度回復するか定量評価
- persistence や geometry fidelity との関係を測定

### 4. Observer の Force 化実験
既存の `phase_shift_observer` や `grid_space_observer` を、単なる観測ではなく「観測結果をForceとして出力する」形に変換する実験。

---

## 長期ビジョン（hubCUBEが目指すもの）

1. LLMはグローバル状態を持たない
2. すべての状態遷移は Dynamics Solver を通じて物理的プロセスとして実現
3. Force / Constraint / Evaluation が明確に分離され、個別に実験・改善可能
4. 任意の推論エンジン（LLM以外も）が同じ PhasePacket インターフェースで接続可能
5. residue / tension / phase のダイナミクスを定量的に研究できるプラットフォームになる

---

## 次のアクション（おすすめ順）

1. **即実行推奨**: `constraints/` 作成 + `MinimalDynamicsSolver` のプロトタイプ
2. Phase 1 の4項目を1つずつ小さな実験として実装（各々1ファイルで完結する形）
3. 既存のレガシーファイルを `experiments/legacy/` に移動してルートをさらにクリーンに
4. ROADMAP.md を定期的に更新しながら進捗を記録

---

**このロードマップは「実験の地図」として機能します。**

各項目は「完成させる」ためではなく、「忠実に実験して何が起きるかを観測する」ために存在します。

何か優先して実験したい項目があれば、すぐにそのモジュールのスケッチや実験用スクリプトを作成します。