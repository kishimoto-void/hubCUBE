# Dynamics

## 役割

Dynamics Solver は、複数の Force と Constraint を統合して**新しい Phase State を生成する唯一の場所**です。

## 原則

- Force Modules は「力」を生成する
- Constraint Modules は「制限」を定義する
- **Dynamics Solver のみが状態を更新する**

## 現在の簡易実装

- `SimpleDynamicsSolver_example.py`：Force のベクトル和 + 簡易 clamp の最小例
- `hubCUBE_SingleRole_Template_v4_ForceBased.py` の `observe_step`：ローカルな簡易 Solver として機能

## 将来的な拡張

本格的な Dynamics Solver では以下のような処理を行う予定：

1. 全 Force をベクトル合成
2. Constraint による制限適用
3. 必要に応じて正規化・安定化処理
4. 新しい Phase State を構築

これにより、Bubble、Repair、Waypoint などの複雑な振る舞いも一貫した枠組みで扱えるようになる。
