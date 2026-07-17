# hubCUBE 開発・実験ロードマップ（改訂版）

**作成日**: 2026-07-17（初版） / **改訂**: 2026-07-17
**作成の背景**: ARCHITECTURE.md / DESIGN.md の設計思想を最も忠実に体現する方向で、役割分離を徹底したロードマップに再構成。

> 「力学をモジュール化する」ことが hubCUBE の最大の強み。
> Forceは「こう動きたい」しか返さない。
> Constraintは「ここまでしか動けない」しか返さない。
> **DynamicsSolverだけが状態を書き換える**。

この原則を最後まで崩さないことが、hubCUBEの価値を最大化する。

---

## 現在の状況（2026-07-17時点）

### 完了している基盤
- `forces/CarryForce_v4.py`：純粋Force Generatorとして良好
- `templates/hubCUBE_SingleRole_Template_v4_ForceBased.py`：最新テンプレート
- ディレクトリ構造の基盤（forces/, templates/, experiments/）

### 大きなギャップ
- DynamicsSolver が独立していない（Template内で状態更新を担っている）
- Constraint層が完全に欠如
- PhaseState の抽象度がまだ低い
- PhasePacket が未定義
- Evaluation（定量評価ループ）が弱い
- Forceの種類が CarryForce のみ

---

## 改訂版ロードマップの全体像

### Phase 1（最優先・心臓部確立）
**目標**: 「State → Forces → Constraints → DynamicsSolver → Next State」の流れを成立させる

#### ① DynamicsSolverの独立（最重要）
**提案ファイル**: `dynamics/MinimalDynamicsSolver.py`

設計原則:
- **Solverだけが状態を更新する**
- Forceは「力ベクトル」のみ返す
- Constraintは「制約」のみ返す
- これらを合成して新PhaseStateを生成する唯一の場所

これがhubCUBEの心臓部になる。

#### ② Constraint層の最小実装
**提案ディレクトリ**: `constraints/`

最低限必要な2つ:
- `BoundaryConstraint.py`（境界制約）
- `GeometryConstraint.py`（幾何制約）

TopologyConstraintはPhase 2以降でOK。

#### ③ PhaseStateの抽象度向上
**提案ファイル**: `state/PhaseState.py`（または `dataclasses` で定義）

現在の `BaseCUBEState` より一段抽象度を上げる。

推奨フィールド例:
- `position`
- `velocity`
- `energy`
- `residue`
- `carry`（carry残量）
- `history`（簡易時系列）
- `waypoint`
- `metadata`

これにより、後のForceやEvaluationが扱いやすくなる。

#### ④ Evaluationの早期導入（Phase 3から繰り上げ）
**目的**: 実験の良し悪しを定量的に比較できるようにする

最低限毎ステップで出すべきメトリクス:
- `energy`
- `residue_norm`
- `entropy`
- `stability`
- `oscillation`

これを `Evaluation` モジュール（または Solver 内で簡易計算）として実装。
Phase 1の段階でこれがあると、後続の実験が非常にやりやすくなる。

**Phase 1 の完了基準**:
- DynamicsSolver が独立して動作する
- Boundary + Geometry Constraint が機能する
- PhaseState が richer になる
- 基本的な定量評価ループが回る

---

### Phase 2（Force拡充とインターフェース整備）

#### Force Library の拡張
CarryForce だけでは世界が狭い。独立した実験として以下を追加：

- `forces/BubbleForce.py`
- `forces/RepairForce.py`
- `forces/MomentumForce.py`
- `forces/NoiseForce.py`
- `forces/GravityForce.py`

それぞれ「このForceを入れたら世界はどう変わるか」を忠実に実験するフェーズ。

#### PhasePacket の定義（非常に重要）
**提案ファイル**: `packet/PhasePacket.py`

設計思想:
- LLMは **State を直接知らない**
- LLMが見るのは **PhasePacket のみ**

将来的な接続形:
```
hubCUBE
  ↓ (DynamicsSolver更新後)
PhasePacket
  ↓
LLM（推論のみ担当）
```

これによりAPI設計も非常にクリーンになる。

#### Observer の将来像
現在の「Observer → 結果」から、将来的には：

```
Observer
  ↓
ObservationForce（観測結果を力として出力）
  ↓
DynamicsSolver
```

「観測」も世界に影響を与える一つの力として扱う方向へ昇華させる。

---

### Phase 3（高度化・長期研究）

- RepairForce の本格化と residue 修復実験
- 長期シミュレーションでの residue / tension / phase の持続性研究
- Evaluation の高度化（risk, priority, repair urgency など）
- 複数Role Hub での力の相互作用実験
- 他プロジェクト（VGE, wCUBE, EmotionalVoidCore）との接続

---

## 長期的なビジョン（hubCUBEが目指す姿）

```
State
  ↓
Force Library（Carry, Bubble, Repair, Momentum...）
  ↓
Constraint Library（Boundary, Geometry, Topology...）
  ↓
DynamicsSolver（唯一の状態更新担当）
  ↓
PhasePacket
  ↓
LLM（推論のみ）
```

hubCUBE は「状態遷移そのもの」を担う**力学ミドルウェア**へと進化する可能性がある。
LLMは推論に専念し、hubCUBEが物理的・力学的な整合性を保証する。

この方向性は、ARCHITECTURE.md・DESIGN.md と完全に一貫しており、
「役割の分離」を最後まで徹底したときに最も美しい形になる。

---

## 次の具体的なアクション（おすすめ順）

1. **最優先**: `dynamics/MinimalDynamicsSolver.py` のプロトタイプ作成
2. `constraints/` ディレクトリ作成 + BoundaryConstraint / GeometryConstraint の最小実装
3. `state/PhaseState.py` の richer 版定義
4. 基本 Evaluation メトリクスを Solver または別モジュールで出力できるようにする
5. PhasePacket のプロトタイプ

各ステップを「小さく・忠実に実験」しながら進めることを推奨します。

---

**このロードマップは「役割分離の設計思想」を軸に再構成しました。**

ご指摘いただいた点を最大限反映しています。
もしこの方向で問題なければ、Phase 1 の最初のモジュール（DynamicsSolver または Constraint）から実際にコードを書き始めます。

何かさらに調整したい点があれば遠慮なくお知らせください。