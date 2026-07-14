#!/usr/bin/env python3
"""
hubCUBE 用 位相ズレ検知モジュール - PhaseShiftObserverCUBE Ver.4.3
位相力学系・ネットワークトポロジー観測器（純粋物理モデル）

【Ver. 4.3 での改善点】
- propagation_trend のリングトポロジー（周期境界）完全対応
  - torch.roll を採用し、(N-1) -> 0 の隣接位相差も平均に含めるように修正
- 動的リンク追跡（Weight, Phase Lag, Stable Duration）の実装
  - コヒーレンス（同期度）に加え、位相差（ラグ）および「同期の継続ステップ数」を内部テンソルで追跡
  - 一時的な位相の重なりと、長期的な安定的同調を明確に判別可能に
- デバイス・精度自動同期に新設テンソル（link_durations）も完全追従
"""

import torch
import math
from dataclasses import dataclass, asdict
from typing import Dict, Any, Tuple, Optional, List

torch.manual_seed(42)


@dataclass
class PhaseCubeConfig:
    num_positions: int = 5
    phase_history_len: int = 128
    slip_threshold: float = 0.8
    acceleration_threshold: float = 0.4
    jerk_threshold: float = 0.25
    variance_threshold: float = 0.5
    anomaly_threshold: float = 0.35
    dt_min: float = 1e-5
    link_threshold: float = 0.60          # coherence > this でリンク生成
    # 重み付きRMSの重み係数 (slip, accel, jerk, variance, local)
    rms_weights: Tuple[float, float, float, float, float] = (0.25, 0.20, 0.15, 0.25, 0.15)


@dataclass
class PhaseMetrics:
    anomaly_score: float
    is_anomaly: bool
    
    # --- 高階時間力学ダイナミクス ---
    phase_drift: float              # グローバル位相変化量/ステップ (rad)  ※dt=1基準
    phase_acceleration: float       # グローバル位相加速度 (rad/step^2)
    phase_jerk: float               # グローバル位相加加速度 (rad/step^3)
    phase_kinetic_energy: float     # 位相運動エネルギー (E_k = 0.5 * mean(v^2))
    phase_slip: bool                # 急激な位相跳躍の判定
    
    # --- 同期構造トポロジー & ネットワーク ---
    circular_variance: float        # 全体ポジション間の位相分散 (1-R)
    order_parameter_velocity: float # 同期秩序変数 R の時間変化率 dR/dt
    local_coherence: float          # 局所健全度 (1.0=正常、max+mean ハイブリッド)
    most_isolated_node_idx: int     # 最も同期から脱落しているノードのインデックス
    most_isolated_coherence: float  # 最も同期から脱落しているノードの同期度 (負値=反位相も可)
    propagation_trend: float        # 隣接ノード間位相勾配の平均（伝播方向の目安・リングトポロジー対応）
    
    # --- 周波数・スペクトル特性 ---
    dominant_frequency: float       # FFT主周波数成分（履歴長に対する正規化周波数 0〜0.5）
    spectral_entropy: float         # 周波数スペクトルの乱雑さ (0=純粋周期, 1=カオス的)
    long_term_drift_trend: float    # 履歴全体の平均ドリフト方向
    
    coherence: float                # 総合同期コヒーレンス (秩序変数 R)
    num_links: int                  # 自動生成された位相同期リンク数
    step: int


class PhaseHistory:
    """高速なテンソルベースのリングバッファ履歴管理（CUDA・マルチデバイス対応）"""
    def __init__(self, maxlen: int, device: torch.device = torch.device("cpu"), dtype: torch.dtype = torch.float32):
        self.maxlen = maxlen
        self.device = device
        self.dtype = dtype
        self.phases = torch.zeros(maxlen, device=device, dtype=dtype)
        self.drifts = torch.zeros(maxlen, device=device, dtype=dtype)
        self.size = 0
        self.pointer = 0

    def append(self, phase: float, drift: float):
        self.phases[self.pointer] = phase
        self.drifts[self.pointer] = drift
        self.pointer = (self.pointer + 1) % self.maxlen
        if self.size < self.maxlen:
            self.size += 1

    def get_phase_tensor(self) -> torch.Tensor:
        if self.size == 0:
            return torch.tensor([], device=self.device, dtype=self.dtype)
        if self.size < self.maxlen:
            return self.phases[:self.size]
        return torch.cat([self.phases[self.pointer:], self.phases[:self.pointer]])

    def get_drift_tensor(self) -> torch.Tensor:
        if self.size == 0:
            return torch.tensor([], device=self.device, dtype=self.dtype)
        if self.size < self.maxlen:
            return self.drifts[:self.size]
        return torch.cat([self.drifts[self.pointer:], self.drifts[:self.pointer]])

    def to(self, device: torch.device, dtype: torch.dtype):
        self.device = device
        self.dtype = dtype
        self.phases = self.phases.to(device=device, dtype=dtype)
        self.drifts = self.drifts.to(device=device, dtype=dtype)
        return self

    def to_dict(self) -> Dict[str, List[float]]:
        return {
            "phases": self.get_phase_tensor().cpu().tolist(),
            "drifts": self.get_drift_tensor().cpu().tolist()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, List[float]], maxlen: int, device: torch.device = torch.device("cpu"), dtype: torch.dtype = torch.float32) -> "PhaseHistory":
        history = cls(maxlen, device=device, dtype=dtype)
        phases = data.get("phases", [])
        drifts = data.get("drifts", [])
        n = min(len(phases), maxlen)
        for i in range(n):
            history.append(phases[i], drifts[i])
        return history

    def __len__(self):
        return self.size


class PhaseShiftObserverCUBE:
    """hubCUBE連携用 多次元位相同期トポロジー観測器（Ver. 4.3）"""
    
    VERSION = "4.3"
    
    def __init__(self, config: Optional[PhaseCubeConfig] = None):
        self.config = config or PhaseCubeConfig()
        self.device = torch.device("cpu")
        self.dtype = torch.float32
        
        self.history = PhaseHistory(self.config.phase_history_len, device=self.device, dtype=self.dtype)
        self.phase_per_position = torch.zeros(self.config.num_positions, device=self.device, dtype=self.dtype)
        self.prev_phase_per_position = torch.zeros(self.config.num_positions, device=self.device, dtype=self.dtype)
        
        # リンクごとの同期継続ステップ数を追跡するマトリクス
        self.link_durations = torch.zeros((self.config.num_positions, self.config.num_positions), device=self.device, dtype=torch.int32)
        
        self.current_global_phase = 0.0
        self.prev_phase_acceleration = 0.0
        self.prev_order_parameter = 1.0
        self.step_count = 0

    def reset(self):
        """実験・セッションリセット用"""
        self.history = PhaseHistory(self.config.phase_history_len, device=self.device, dtype=self.dtype)
        self.phase_per_position = torch.zeros(self.config.num_positions, device=self.device, dtype=self.dtype)
        self.prev_phase_per_position = torch.zeros(self.config.num_positions, device=self.device, dtype=self.dtype)
        self.link_durations = torch.zeros((self.config.num_positions, self.config.num_positions), device=self.device, dtype=torch.int32)
        self.current_global_phase = 0.0
        self.prev_phase_acceleration = 0.0
        self.prev_order_parameter = 1.0
        self.step_count = 0

    def create_initial_state(self) -> Dict[str, Any]:
        return {
            "status": {
                "phase": 0.0,
                "velocity": 0.0,
                "acceleration": 0.0,
                "jerk": 0.0,
                "kinetic_energy": 0.0,
                "coherence": 1.0,
                "order_param_velocity": 0.0,
                "dominant_freq": 0.0,
                "spectral_entropy": 0.0,
                "most_isolated_node": 0,
                "propagation_trend": 0.0,
            },
            "step": 0,
            "links": [],
            "version": self.VERSION,
        }

    def _update_device_and_dtype(self, ref_tensor: torch.Tensor):
        """入力にデバイスや型を完全に同期（新規追加した link_durations も対象）"""
        if ref_tensor.device != self.device or ref_tensor.dtype != self.dtype:
            self.device = ref_tensor.device
            self.dtype = ref_tensor.dtype
            self.phase_per_position = self.phase_per_position.to(device=self.device, dtype=self.dtype)
            self.prev_phase_per_position = self.prev_phase_per_position.to(device=self.device, dtype=self.dtype)
            self.link_durations = self.link_durations.to(device=self.device) # int32型は維持
            self.history.to(self.device, self.dtype)

    @staticmethod
    def _shortest_angle_diff(a: Any, b: Any) -> Any:
        """2つの角度間の最短経路差分を -π 〜 π の範囲で計算（テンソル・スカラー両用）"""
        if torch.is_tensor(a) or torch.is_tensor(b):
            ref = a if torch.is_tensor(a) else b
            a_t = torch.as_tensor(a, device=ref.device, dtype=ref.dtype)
            b_t = torch.as_tensor(b, device=ref.device, dtype=ref.dtype)
            diff = a_t - b_t
            return torch.remainder(diff + math.pi, 2 * math.pi) - math.pi
        else:
            return (a - b + math.pi) % (2 * math.pi) - math.pi

    def _compute_order_parameter(self, phases: torch.Tensor) -> float:
        if len(phases) == 0:
            return 0.0
        complex_sum = torch.sum(torch.exp(1j * phases))
        return torch.abs(complex_sum).item() / len(phases)

    def _analyze_spectrum(self) -> Tuple[float, float]:
        """主周波数とスペクトルエントロピー"""
        if len(self.history) < 32:
            return 0.0, 0.0
        
        phase_tensor = self.history.get_phase_tensor()
        complex_signal = torch.exp(1j * phase_tensor)
        
        fft_vals = torch.fft.fft(complex_signal)
        fft_power = torch.abs(fft_vals)[1:len(phase_tensor)//2]
        
        if len(fft_power) == 0 or torch.sum(fft_power) < 1e-8:
            return 0.0, 0.0
        
        dominant_idx = int(torch.argmax(fft_power)) + 1
        dominant_freq = dominant_idx / len(phase_tensor)
        
        prob_dist = fft_power / torch.sum(fft_power)
        prob_dist = torch.clamp(prob_dist, min=1e-9)
        entropy = -torch.sum(prob_dist * torch.log(prob_dist)).item()
        
        max_entropy = math.log(len(prob_dist))
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
        
        return dominant_freq, normalized_entropy

    def step(
        self, 
        x: torch.Tensor, 
        dt: float = 1.0,
        external_phases: Optional[torch.Tensor] = None
    ) -> Tuple[Dict[str, Any], PhaseMetrics]:
        """
        1ステップ観測実行。
        """
        if external_phases is not None:
            self._update_device_and_dtype(external_phases)
        else:
            self._update_device_and_dtype(x)

        effective_dt = max(float(dt), self.config.dt_min)
        val = float(x.mean()) if x.numel() > 1 else float(x)

        # 1. グローバル位相更新
        self.current_global_phase = (self.current_global_phase + val * 0.3) % (2 * math.pi)

        # 2. 各ポジション位相の決定
        if external_phases is not None:
            if external_phases.numel() != self.config.num_positions:
                ext = external_phases.flatten()
                if ext.numel() > 0:
                    new_phase_per_pos = torch.full(
                        (self.config.num_positions,), float(ext.mean()),
                        device=self.device, dtype=self.dtype
                    ) % (2 * math.pi)
                else:
                    new_phase_per_pos = self.phase_per_position.clone()
            else:
                new_phase_per_pos = torch.remainder(external_phases, 2 * math.pi).clone()
        else:
            spread = 0.05 + abs(val) * 0.1
            noise = torch.randn(self.config.num_positions, device=self.device, dtype=self.dtype)
            phase_update = noise * spread + val * 0.2
            new_phase_per_pos = (self.phase_per_position + phase_update) % (2 * math.pi)

        # 3. ダイナミクス（速度・加速度・ジャーク）
        prev_phase = float(self.history.phases[self.history.pointer - 1]) if len(self.history) > 0 else self.current_global_phase
        phase_drift = self._shortest_angle_diff(self.current_global_phase, prev_phase)
        
        prev_drift = float(self.history.drifts[self.history.pointer - 1]) if len(self.history) > 0 else phase_drift
        phase_accel = (phase_drift - prev_drift) / effective_dt
        
        phase_jerk = (phase_accel - self.prev_phase_acceleration) / effective_dt

        # 4. 位相運動エネルギー計算
        pos_diffs = self._shortest_angle_diff(new_phase_per_pos, self.prev_phase_per_position)
        pos_vel = pos_diffs / effective_dt
        kinetic_energy = 0.5 * torch.mean(pos_vel ** 2).item()

        # 5. 同期解析
        order_param = self._compute_order_parameter(new_phase_per_pos)
        circular_var = 1.0 - order_param
        order_param_vel = (order_param - self.prev_order_parameter) / effective_dt

        # 6. コヒーレンス行列
        phases_col = new_phase_per_pos.unsqueeze(1)
        phases_row = new_phase_per_pos.unsqueeze(0)
        phase_diff_matrix = self._shortest_angle_diff(phases_col, phases_row)
        coherence_matrix = torch.cos(phase_diff_matrix)

        # 最も孤立したノードの特定
        if self.config.num_positions > 1:
            node_coherence = (torch.sum(coherence_matrix, dim=1) - 1.0) / (self.config.num_positions - 1)
            most_isolated_node_idx = int(torch.argmin(node_coherence).item())
            most_isolated_coherence = float(node_coherence[most_isolated_node_idx])
            
            # 【リングトポロジー対応】
            # torch.roll により、N-1 -> 0 への接続も含めた循環隣接位相差を一括取得
            shifted_phases = torch.roll(new_phase_per_pos, shifts=-1)
            diff_adjacent = self._shortest_angle_diff(shifted_phases, new_phase_per_pos)
            propagation_trend = float(torch.mean(diff_adjacent).item())
        else:
            most_isolated_node_idx = 0
            most_isolated_coherence = 1.0
            propagation_trend = 0.0

        # 局所コヒーレンス
        global_complex = torch.mean(torch.exp(1j * new_phase_per_pos))
        mean_angle = torch.atan2(global_complex.imag, global_complex.real).item()
        local_diffs = torch.abs(self._shortest_angle_diff(new_phase_per_pos, mean_angle))
        
        hybrid_dev = 0.9 * local_diffs.max().item() + 0.1 * local_diffs.mean().item()
        local_coherence = max(0.0, 1.0 - hybrid_dev / math.pi)

        # 7. 履歴更新と状態遷移
        self.history.append(self.current_global_phase, phase_drift)
        self.prev_phase_per_position = self.phase_per_position.clone()
        self.phase_per_position = new_phase_per_pos.clone()
        self.prev_order_parameter = order_param
        self.prev_phase_acceleration = phase_accel
        self.step_count += 1

        # 8. スペクトル解析
        dominant_freq, spectral_entropy = self._analyze_spectrum()
        drift_tensor = self.history.get_drift_tensor()
        long_term_drift = (
            torch.mean(drift_tensor).item() if len(self.history) > 0 else 0.0
        )

        # 9. 異常スコア
        slip_score = min(1.0, abs(phase_drift) / self.config.slip_threshold)
        accel_score = min(1.0, abs(phase_accel) / self.config.acceleration_threshold)
        jerk_score = min(1.0, abs(phase_jerk) / self.config.jerk_threshold)
        var_score = min(1.0, circular_var / self.config.variance_threshold)
        local_score = 1.0 - local_coherence

        w = self.config.rms_weights
        weighted_sum_sq = (
            w[0] * (slip_score ** 2) +
            w[1] * (accel_score ** 2) +
            w[2] * (jerk_score ** 2) +
            w[3] * (var_score ** 2) +
            w[4] * (local_score ** 2)
        )
        anomaly_score = math.sqrt(weighted_sum_sq)
        is_anomaly = anomaly_score > self.config.anomaly_threshold

        # 10. 【動的リンク追跡】
        active_links_mask = coherence_matrix > self.config.link_threshold
        # コヒーレンスが閾値を超えたリンクの持続ステップ数をインクリメント、それ以外は0にリセット
        self.link_durations = torch.where(active_links_mask, self.link_durations + 1, torch.zeros_like(self.link_durations))

        links: List[Tuple[int, int, float, float, int]] = []
        n = self.config.num_positions
        for i in range(n):
            for j in range(i + 1, n):
                if active_links_mask[i, j]:
                    coh = float(coherence_matrix[i, j].item())
                    # phase_lag: 最短位相差の絶対値
                    lag = float(torch.abs(phase_diff_matrix[i, j]).item())
                    dur = int(self.link_durations[i, j].item())
                    links.append((i, j, round(coh, 4), round(lag, 4), dur))

        # 11. 返却用状態マップ
        new_state = self.create_initial_state()
        new_state["status"].update({
            "phase": self.current_global_phase,
            "velocity": phase_drift,
            "acceleration": phase_accel,
            "jerk": phase_jerk,
            "kinetic_energy": round(kinetic_energy, 4),
            "coherence": round(order_param, 3),
            "order_param_velocity": round(order_param_vel, 4),
            "dominant_freq": round(dominant_freq, 3),
            "spectral_entropy": round(spectral_entropy, 3),
            "most_isolated_node": most_isolated_node_idx,
            "propagation_trend": round(propagation_trend, 4),
        })
        new_state["step"] = self.step_count
        new_state["links"] = links

        metrics = PhaseMetrics(
            anomaly_score=round(anomaly_score, 4),
            is_anomaly=is_anomaly,
            phase_drift=round(phase_drift, 4),
            phase_acceleration=round(phase_accel, 4),
            phase_jerk=round(phase_jerk, 4),
            phase_kinetic_energy=round(kinetic_energy, 4),
            phase_slip=abs(phase_drift) > self.config.slip_threshold,
            circular_variance=round(circular_var, 4),
            order_parameter_velocity=round(order_param_vel, 4),
            local_coherence=round(local_coherence, 4),
            most_isolated_node_idx=most_isolated_node_idx,
            most_isolated_coherence=round(most_isolated_coherence, 4),
            propagation_trend=round(propagation_trend, 4),
            dominant_frequency=round(dominant_freq, 3),
            spectral_entropy=round(spectral_entropy, 3),
            long_term_drift_trend=round(long_term_drift, 4),
            coherence=new_state["status"]["coherence"],
            num_links=len(links),
            step=self.step_count,
        )

        return new_state, metrics

    def to_dict(self) -> Dict[str, Any]:
        """hubCUBE保存用（完全永続化）"""
        return {
            "config": asdict(self.config),
            "step_count": self.step_count,
            "current_global_phase": self.current_global_phase,
            "prev_phase_acceleration": self.prev_phase_acceleration,
            "phase_per_position": self.phase_per_position.cpu().tolist(),
            "prev_phase_per_position": self.prev_phase_per_position.cpu().tolist(),
            "link_durations": self.link_durations.cpu().tolist(), # 追加
            "prev_order_parameter": self.prev_order_parameter,
            "history": self.history.to_dict(),
            "version": self.VERSION,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PhaseShiftObserverCUBE":
        """hubCUBE復元用"""
        config = PhaseCubeConfig(**data["config"])
        cube = cls(config)
        cube.step_count = data["step_count"]
        cube.current_global_phase = data["current_global_phase"]
        cube.prev_phase_acceleration = data["prev_phase_acceleration"]
        cube.phase_per_position = torch.tensor(data["phase_per_position"])
        cube.prev_phase_per_position = torch.tensor(data["prev_phase_per_position"])
        cube.prev_order_parameter = data["prev_order_parameter"]
        
        # 後方互換性：古い辞書に link_durations がない場合は 0 で初期化
        if "link_durations" in data:
            cube.link_durations = torch.tensor(data["link_durations"], dtype=torch.int32)
        else:
            cube.link_durations = torch.zeros((config.num_positions, config.num_positions), dtype=torch.int32)
            
        if "history" in data:
            cube.history = PhaseHistory.from_dict(data["history"], config.phase_history_len)
        return cube


# ====================== デモ & 検証 ======================
if __name__ == "__main__":
    print("=== PhaseShiftObserverCUBE 4.3 検証実行 ===")
    obs = PhaseShiftObserverCUBE(PhaseCubeConfig(num_positions=4))
    
    # 意図的に安定同期状態を作り、ステップを刻む
    # 0, 1 はほぼ同相(同期), 2, 3 は反相
    test_phases = torch.tensor([0.0, 0.05, math.pi, math.pi + 0.1])
    
    for step in range(5):
        state, metrics = obs.step(torch.tensor([0.1]), external_phases=test_phases)
        print(f"Step {step+1}:")
        print(f"  └─ Propagation Trend (Ring): {metrics.propagation_trend:.4f}")
        print(f"  └─ Generated Links (i, j, weight, lag, duration):")
        for link in state["links"]:
            print(f"     └─ Node {link[0]} <-> {link[1]} | Coherence: {link[2]:.4f} | Lag: {link[3]:.4f} | Duration: {link[4]} steps")
