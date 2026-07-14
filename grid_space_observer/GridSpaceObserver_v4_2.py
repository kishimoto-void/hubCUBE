#!/usr/bin/env python3
"""
GridSpaceObserver [Ver 4.2] - Autocorrelative Spatiotemporal Geometric Analyzer
- 状態空間における幾何的変形、時間密度、流動流量、および自己相関周期性を無感情に測定する極限観測器。
- Ver 4.2: 
  1. 解析コアのモジュール化リファクタリング (Geometry / Time / Density への完全分割)
  2. tanh による偏差指数の [0.0, 1.0) ソフトクリップ化
  3. trajectory_len に基づく正規化アトラクタ寿命 (norm_attractor_age) の出力
  4. コンソール用アスキー・フローレンダラー (render_flow_matrix) の新規搭載
"""

import torch
from dataclasses import dataclass
from typing import Tuple, Dict, Any, List, Optional
import math

# ============================================================
# 構造化データ保持器
# ============================================================
@dataclass
class BaseCUBEState:
    axis: torch.Tensor
    residue: torch.Tensor
    tension: torch.Tensor
    status: Dict[str, float]
    links: List[Tuple[int, int, float]]
    step: int = 0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class MeasurementMetrics:
    deviation_index: float           # [0~1] tanhソフトクリップ済み3軸統合偏差
    is_out_of_bounds: bool           # 物理境界逸脱フラグ
    geometric_distortion_norm: float # 幾何歪み平均
    coherence: float                 # 軌道コヒーレンス
    entropy: float                   # 時間・空間の総合エントロピー
    active_couplings: int            # センサーチャネル間結合数
    out_of_bounds_duration: int      # 逸脱継続時間
    sensor_signals: Dict[str, Any]   # 各測定モジュールから出力される生物理量


# ============================================================
# 計測ユニット基底
# ============================================================
class SingleRoleCUBE:
    def __init__(
        self,
        role_name: str = "Observer",
        num_positions: int = 5,
        residue_decay: float = 0.87,
        link_threshold: float = 0.15,
        boundary_threshold: float = 0.48,
        residue_cap: float = 3.0,
    ):
        self.role_name = role_name
        self.num_positions = num_positions
        self.residue_decay = residue_decay
        self.link_threshold = link_threshold
        self.boundary_threshold = boundary_threshold
        self.residue_cap = residue_cap
        
        from collections import deque
        self.deviation_history = deque(maxlen=12)
        self.ema_dist = 0.0
        self.ema_ten = 0.0
        self.out_of_bounds_duration = 0

    def create_initial_state(self) -> BaseCUBEState:
        return BaseCUBEState(
            axis=torch.zeros(self.num_positions),
            residue=torch.zeros(self.num_positions),
            tension=torch.zeros(self.num_positions),
            status={"phase": 0.0, "coherence": 1.0, "entropy": 0.0},
            links=[],
            metadata={}
        )

    def _update_statistical_metrics(self, dist_norm: float, ten_norm: float) -> float:
        self.deviation_history.append(dist_norm)
        alpha = 0.2
        self.ema_dist = (1 - alpha) * self.ema_dist + alpha * dist_norm
        self.ema_ten = (1 - alpha) * self.ema_ten + alpha * ten_norm
        return sum(self.deviation_history) / max(1, len(self.deviation_history))

    def build_coupling_links(self, values: torch.Tensor) -> List[Tuple[int, int, float]]:
        if self.num_positions < 2:
            return []
        diff = values.unsqueeze(1) - values.unsqueeze(0)
        abs_i = values.abs().unsqueeze(1)
        strength_matrix = diff.abs() * 0.7 + abs_i * 0.3
        
        triu_indices = torch.triu_indices(self.num_positions, self.num_positions, offset=1)
        strengths = strength_matrix[triu_indices[0], triu_indices[1]]
        
        mask = strengths > self.link_threshold
        filtered_indices = triu_indices[:, mask]
        filtered_strengths = strengths[mask]
        
        links = []
        for idx in range(filtered_strengths.size(0)):
            i = int(filtered_indices[0, idx])
            j = int(filtered_indices[1, idx])
            w = float(filtered_strengths[idx])
            links.append((i, j, round(w, 3)))
            
        return sorted(links, key=lambda x: x[2], reverse=True)[:4]

    def _compute_core(self, state: BaseCUBEState, x: torch.Tensor, *args, **kwargs) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, Dict[str, Any]]:
        new_axis = state.axis * 0.6 + x.mean() * 0.4
        new_res = torch.clamp(state.residue * self.residue_decay + (new_axis - state.axis), -self.residue_cap, self.residue_cap)
        new_ten = (new_res - state.residue).abs()
        return new_axis, new_res, new_ten, {}

    def observe_step(self, state: BaseCUBEState, x: torch.Tensor, *args, **kwargs) -> Tuple[BaseCUBEState, MeasurementMetrics]:
        new_axis, new_res, new_ten, sensor_signals = self._compute_core(state, x, *args, **kwargs)
        
        dist_norm = float(new_res.abs().mean())
        ten_m = float(new_ten.mean())
        sustained = self._update_statistical_metrics(dist_norm, ten_m)
        
        links = self.build_coupling_links(new_res)
        
        new_status = state.status.copy()
        new_status["coherence"] = max(0.0, min(1.0, 1.0 - ten_m * 0.8))
        new_status["entropy"] = max(0.0, min(1.0, dist_norm * 0.6))
        
        deviation_index = sensor_signals.get("deviation_index", min(1.0, dist_norm * 2.8 + sustained * 1.6))
        is_out_of_bounds = deviation_index > self.boundary_threshold
        self.out_of_bounds_duration = self.out_of_bounds_duration + 1 if is_out_of_bounds else 0

        new_state = BaseCUBEState(
            axis=new_axis, residue=new_res, tension=new_ten,
            status=new_status, links=links, step=state.step + 1,
            metadata=state.metadata
        )
        
        metrics = MeasurementMetrics(
            deviation_index=round(deviation_index, 4),
            is_out_of_bounds=is_out_of_bounds,
            geometric_distortion_norm=round(dist_norm, 4),
            coherence=round(new_status["coherence"], 3),
            entropy=round(new_status["entropy"], 3),
            active_couplings=len(links),
            out_of_bounds_duration=self.out_of_bounds_duration,
            sensor_signals=sensor_signals
        )
        
        return new_state, metrics


# ============================================================
# GridSpaceObserver 実装 (Ver. 4.2)
# ============================================================
class GridSpaceObserver(SingleRoleCUBE):
    VERSION = "4.2"
    
    def __init__(
        self,
        num_positions: int = 5,
        grid_resolution: int = 8,
        trajectory_len: int = 32,
        bpm_history_len: int = 64,
        state_bound: float = 2.5,
        break_sensitivity: float = 0.35,
        decay_rate: float = 0.985,
        calibration_steps: int = 15,
        smoothing_alpha: float = 0.30,
        **kwargs
    ):
        super().__init__(role_name="GridObserver", num_positions=num_positions, **kwargs)
        
        self.grid_res = grid_resolution
        self.grid_cells = grid_resolution * grid_resolution
        self.trajectory_len = trajectory_len
        self.bpm_history_len = bpm_history_len
        self.state_bound = state_bound
        self.break_sensitivity = break_sensitivity
        self.decay_rate = decay_rate
        self.calibration_steps = calibration_steps
        self.smoothing_alpha = smoothing_alpha
        
        self.device = torch.device("cpu")
        self.dtype = torch.float32
        
        # 各種バッファ
        self.trajectory_buffer: Optional[torch.Tensor] = None
        self.bpm_history: Optional[torch.Tensor] = None
        self.bpm_pointer = 0
        self.bpm_history_size = 0
        
        # 流動マトリクス
        self.prev_grid_indices: Optional[torch.Tensor] = None
        self.flow_matrix = torch.zeros((num_positions, self.grid_cells, self.grid_cells), dtype=torch.float32)
        self.grid_bpm_sum = torch.zeros((num_positions, self.grid_cells), dtype=torch.float32)
        self.grid_counts_total = torch.zeros((num_positions, self.grid_cells), dtype=torch.float32)
        
        self.attractor_age = torch.zeros(num_positions, dtype=torch.int32)
        
        # 校正回路
        self.calibration_counter = 0
        self.noise_floor_curvature = torch.zeros(num_positions, dtype=torch.float32)

    def _update_device_and_dtype(self, ref: torch.Tensor):
        if ref.device != self.device or ref.dtype != self.dtype:
            self.device = ref.device
            self.dtype = ref.dtype
            
            if self.trajectory_buffer is not None:
                self.trajectory_buffer = self.trajectory_buffer.to(device=self.device, dtype=self.dtype)
            if self.bpm_history is not None:
                self.bpm_history = self.bpm_history.to(device=self.device, dtype=self.dtype)
            if self.prev_grid_indices is not None:
                self.prev_grid_indices = self.prev_grid_indices.to(device=self.device)
                
            self.flow_matrix = self.flow_matrix.to(device=self.device, dtype=self.dtype)
            self.grid_bpm_sum = self.grid_bpm_sum.to(device=self.device, dtype=self.dtype)
            self.grid_counts_total = self.grid_counts_total.to(device=self.device, dtype=self.dtype)
            self.attractor_age = self.attractor_age.to(device=self.device)
            self.noise_floor_curvature = self.noise_floor_curvature.to(device=self.device, dtype=self.dtype)

    @staticmethod
    def _shortest_angle_diff(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
        diff = a - b
        return torch.remainder(diff + math.pi, 2 * math.pi) - math.pi

    def _calculate_bpm_autocorrelation(self, bpm_tensor: torch.Tensor, lag: int = 1) -> torch.Tensor:
        L, N = bpm_tensor.shape
        if L <= lag + 2:
            return torch.zeros(N, device=self.device, dtype=self.dtype)
        
        mean = bpm_tensor.mean(dim=0, keepdim=True)
        variance = bpm_tensor.var(dim=0, unbiased=False, keepdim=True) + 1e-9
        centered = bpm_tensor - mean
        
        val_t = centered[:-lag, :]
        val_lag = centered[lag:, :]
        
        covariance_lag = (val_t * val_lag).mean(dim=0)
        autocorr = covariance_lag / variance.squeeze(0)
        
        autocorr = torch.where(torch.isnan(autocorr) | torch.isinf(autocorr), torch.ones_like(autocorr), autocorr)
        return torch.clamp(autocorr, -1.0, 1.0)

    def _analyze_bpm_spectral_entropy(self, bpm_tensor: torch.Tensor) -> torch.Tensor:
        L, N = bpm_tensor.shape
        if L < 16:
            return torch.zeros(N, device=self.device, dtype=self.dtype)
        
        bpm_std = torch.std(bpm_tensor, dim=0)
        flat_mask = bpm_std < 1e-6
        
        fft_vals = torch.fft.fft(bpm_tensor, dim=0)
        fft_power = torch.abs(fft_vals)[1:L//2, :]
        
        sum_power = torch.sum(fft_power, dim=0, keepdim=True)
        invalid_mask = (sum_power < 1e-8).squeeze(0)
        
        prob_dist = fft_power / (sum_power + 1e-9)
        prob_dist = torch.clamp(prob_dist, min=1e-9)
        
        entropy = -torch.sum(prob_dist * torch.log(prob_dist), dim=0)
        max_entropy = math.log(max(2, L//2 - 1))
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else torch.zeros_like(entropy)
        
        normalized_entropy[flat_mask | invalid_mask] = 0.0
        return normalized_entropy

    # ============================================================
    # Ver 4.2 サブモジュール化：分割処理メソッド群
    # ============================================================
    def _project_and_normalize(self, state: BaseCUBEState, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        位置、速度ベクトルの射影、バッファ蓄積、および境界値の動的エンベロープ追従
        """
        if x.numel() == self.num_positions:
            current_pos = x.clone()
        elif x.numel() == 1:
            current_pos = torch.full((self.num_positions,), float(x.item()), device=self.device, dtype=self.dtype)
        else:
            current_pos = torch.full((self.num_positions,), float(x.mean()), device=self.device, dtype=self.dtype)
            
        prev_pos = state.axis
        current_vel = current_pos - prev_pos
        current_state_2d = torch.stack([current_pos, current_vel], dim=1)
        
        # 緩やかな境界スケーリング追従
        current_max = float(current_pos.abs().max().item())
        self.state_bound = 0.98 * self.state_bound + 0.02 * max(current_max * 1.5, 1.0)
        
        if self.trajectory_buffer is None:
            self.trajectory_buffer = current_state_2d.unsqueeze(0).repeat(self.trajectory_len, 1, 1)
        else:
            self.trajectory_buffer = torch.roll(self.trajectory_buffer, shifts=-1, dims=0)
            self.trajectory_buffer[-1] = current_state_2d

        traj = self.trajectory_buffer.transpose(0, 1)  # (N, H, 2)
        return current_pos, current_vel, traj

    def _analyze_geometry(self, traj: torch.Tensor, state: BaseCUBEState) -> Dict[str, torch.Tensor]:
        """
        幾何プロファイルの測定、および曲率に対するノイズ床(EMA)減算回路の適用
        """
        mean_traj = traj.mean(dim=1, keepdim=True)
        centered_traj = traj - mean_traj
        
        cov_divisor = max(2.0, float(self.trajectory_len - 1))
        cov_matrices = torch.bmm(centered_traj.transpose(1, 2), centered_traj) / cov_divisor
        cov_matrices = cov_matrices + torch.eye(2, device=self.device, dtype=self.dtype).unsqueeze(0) * 1e-5
        
        eigenvalues, _ = torch.linalg.eigh(cov_matrices)
        eigenvalues = torch.clamp(eigenvalues, min=1e-8)
        
        major_radius = torch.sqrt(eigenvalues[:, 1])
        minor_radius = torch.sqrt(eigenvalues[:, 0])
        node_dispersions = eigenvalues.sum(dim=1)
        node_degeneracy = 1.0 - (eigenvalues[:, 0] / eigenvalues[:, 1])

        # 相空間の曲率計算
        if self.trajectory_len >= 3:
            pts = self.trajectory_buffer[-3:]
            u = pts[1] - pts[0]
            w = pts[2] - pts[1]
            theta_u = torch.atan2(u[:, 1], u[:, 0])
            theta_w = torch.atan2(w[:, 1], w[:, 0])
            raw_curvature = torch.abs(self._shortest_angle_diff(theta_w, theta_u))
        else:
            raw_curvature = torch.zeros(self.num_positions, device=self.device, dtype=self.dtype)

        # ドリフト追従
        if self.calibration_counter < self.calibration_steps:
            self.calibration_counter += 1
            self.noise_floor_curvature = 0.8 * self.noise_floor_curvature + 0.2 * raw_curvature
            node_curvature = torch.clamp(raw_curvature - self.noise_floor_curvature, min=0.0) * 0.1
        else:
            self.noise_floor_curvature = 0.999 * self.noise_floor_curvature + 0.001 * raw_curvature
            node_curvature = torch.clamp(raw_curvature - self.noise_floor_curvature, min=0.0)

        return {
            "major_radius": major_radius,
            "minor_radius": minor_radius,
            "dispersions": node_dispersions,
            "degeneracy": node_degeneracy,
            "curvature": node_curvature
        }

    def _analyze_time(self, current_vel: torch.Tensor, dt_val: float) -> Dict[str, torch.Tensor]:
        """
        自己相関周期、変動、およびスペクトルエントロピーの解析
        """
        instant_bpm = torch.abs(current_vel) / dt_val
        
        if self.bpm_history is None:
            self.bpm_history = torch.zeros((self.bpm_history_len, self.num_positions), device=self.device, dtype=self.dtype)
            
        self.bpm_history[self.bpm_pointer] = instant_bpm
        self.bpm_pointer = (self.bpm_pointer + 1) % self.bpm_history_len
        if self.bpm_history_size < self.bpm_history_len:
            self.bpm_history_size += 1
            
        if self.bpm_history_size < self.bpm_history_len:
            sorted_bpm = self.bpm_history[:self.bpm_history_size]
        else:
            sorted_bpm = torch.cat([self.bpm_history[self.bpm_pointer:], self.bpm_history[:self.bpm_pointer]], dim=0)

        moving_bpm = sorted_bpm.mean(dim=0)
        bpm_variance = sorted_bpm.var(dim=0, unbiased=False) + 1e-9
        bpm_entropy = self._analyze_bpm_spectral_entropy(sorted_bpm)
        autocorr_lag1 = self._calculate_bpm_autocorrelation(sorted_bpm, lag=1)
        autocorr_lag2 = self._calculate_bpm_autocorrelation(sorted_bpm, lag=2)

        return {
            "instant_bpm": instant_bpm,
            "moving_bpm": moving_bpm,
            "bpm_variance": bpm_variance,
            "bpm_entropy": bpm_entropy,
            "autocorr_lag1": autocorr_lag1,
            "autocorr_lag2": autocorr_lag2
        }

    def _analyze_density_and_flow(self, traj: torch.Tensor, instant_bpm: torch.Tensor, geom: Dict[str, torch.Tensor], state: BaseCUBEState) -> Dict[str, Any]:
        """
        空間離散エントロピー、流動遷移、およびノード別アトラクタ寿命の更新
        """
        normalized_traj = (traj + self.state_bound) / (2.0 * self.state_bound)
        grid_coords = torch.clamp((normalized_traj * self.grid_res).long(), 0, self.grid_res - 1)
        flat_indices = grid_coords[:, :, 0] * self.grid_res + grid_coords[:, :, 1]
        
        grid_counts = torch.zeros((self.num_positions, self.grid_cells), device=self.device, dtype=self.dtype)
        grid_counts.scatter_add_(1, flat_indices, torch.ones_like(flat_indices, dtype=self.dtype))
        prob_distributions = torch.clamp(grid_counts / self.trajectory_len, min=1e-9)
        
        node_grid_entropies = -torch.sum(prob_distributions * torch.log(prob_distributions), dim=1)
        max_grid_entropy = math.log(self.grid_cells)
        node_grid_entropies = node_grid_entropies / max_grid_entropy if max_grid_entropy > 0 else torch.zeros_like(node_grid_entropies)

        current_grid = flat_indices[:, -1]
        
        self.flow_matrix = self.flow_matrix * self.decay_rate
        self.grid_bpm_sum = self.grid_bpm_sum * self.decay_rate
        self.grid_counts_total = self.grid_counts_total * self.decay_rate

        if self.prev_grid_indices is not None:
            self.flow_matrix[torch.arange(self.num_positions), self.prev_grid_indices, current_grid] += instant_bpm
        self.prev_grid_indices = current_grid.clone()

        self.grid_bpm_sum[torch.arange(self.num_positions), current_grid] += instant_bpm
        self.grid_counts_total[torch.arange(self.num_positions), current_grid] += 1.0

        # アトラクタ破綻（相転移）検出
        prev_disp = state.metadata.get("node_dispersion_tensor", geom["dispersions"])
        prev_rad = state.metadata.get("node_major_radius_tensor", geom["major_radius"])
        
        if not isinstance(prev_disp, torch.Tensor):
            prev_disp = torch.full_like(geom["dispersions"], float(prev_disp))
        if not isinstance(prev_rad, torch.Tensor):
            prev_rad = torch.full_like(geom["major_radius"], float(prev_rad))

        disp_diff = (geom["dispersions"] - prev_disp).abs()
        rad_diff = (geom["major_radius"] - prev_rad).abs()
        
        relative_disp_dev = disp_diff / (prev_disp + 1e-6)
        relative_rad_dev = rad_diff / (prev_rad + 1e-6)
        
        is_break = (relative_disp_dev + relative_rad_dev) > self.break_sensitivity
        self.attractor_age = torch.where(is_break, torch.zeros_like(self.attractor_age), self.attractor_age + 1)

        return {
            "grid_entropy": node_grid_entropies,
            "relative_disp_dev": relative_disp_dev,
            "is_break": is_break
        }

    # ============================================================
    # コア演算フロー
    # ============================================================
    def _compute_core(
        self, 
        state: BaseCUBEState, 
        x: torch.Tensor,
        dt: float = 1.0,
        **kwargs
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, Dict[str, Any]]:
        self._update_device_and_dtype(x)
        dt_val = max(float(dt), 1e-5)
        
        # 1. 位置・速度データの取得
        current_pos, current_vel, traj = self._project_and_normalize(state, x)
        
        # 2. サブ解析パイプラインの実行
        geom = self._analyze_geometry(traj, state)
        time_ana = self._analyze_time(current_vel, dt_val)
        dens = self._analyze_density_and_flow(traj, instant_bpm=time_ana["instant_bpm"], geom=geom, state=state)
        
        # 3. 3軸偏差指数の定量評価
        # ① Geometry Deviation (35%)
        geom_dev_tensor = 0.4 * geom["degeneracy"] + 0.3 * torch.clamp(dens["relative_disp_dev"], 0.0, 2.0) + 0.3 * torch.clamp(geom["curvature"] / math.pi, 0.0, 1.0)
        # ② Time Deviation (30%)
        bpm_relative_var = torch.clamp(time_ana["bpm_variance"] / (time_ana["moving_bpm"]**2 + 1e-6), 0.0, 3.0) / 3.0
        time_dev_tensor = 0.3 * bpm_relative_var + 0.3 * time_ana["bpm_entropy"] + 0.4 * (1.0 - torch.clamp(time_ana["autocorr_lag1"], -1.0, 1.0))
        # ③ Density Deviation (35%)
        density_break_penalty = torch.where(dens["is_break"], torch.ones_like(dens["grid_entropy"]) * 0.8, torch.zeros_like(dens["grid_entropy"]))
        dens_dev_tensor = 0.6 * (1.0 - dens["grid_entropy"]) + 0.4 * density_break_penalty

        # 4. ソフトクリッピング & 慣性平滑化
        node_deviations = 0.35 * geom_dev_tensor + 0.30 * time_dev_tensor + 0.35 * dens_dev_tensor
        raw_deviation_index = float(node_deviations.mean().item())

        # [Ver 4.2] 偏差のソフトクリップ (tanh適用による [0, 1) スケーリング)
        raw_deviation_scaled = math.tanh(raw_deviation_index)

        prev_smoothed_dev = state.metadata.get("smoothed_deviation_index", raw_deviation_scaled)
        deviation_index = (1.0 - self.smoothing_alpha) * prev_smoothed_dev + self.smoothing_alpha * raw_deviation_scaled

        # [Ver 4.2] アトラクタ寿命の正規化比率の算出
        norm_attractor_age = torch.clamp(self.attractor_age.to(torch.float32) / self.trajectory_len, 0.0, 1.0)

        # 状態更新用のテンソル・変数の退避
        new_axis = current_pos
        new_res = (1.0 - dens["grid_entropy"] + time_ana["bpm_entropy"]) * self.residue_cap * 0.5
        tension_factor = dens["relative_disp_dev"].mean().item() * (float(time_ana["bpm_variance"].mean().item()) + 0.05) * 5.0
        new_ten = torch.full((self.num_positions,), tension_factor, device=self.device, dtype=self.dtype)

        state.metadata["node_dispersion_tensor"] = geom["dispersions"].clone()
        state.metadata["node_major_radius_tensor"] = geom["major_radius"].clone()
        state.metadata["smoothed_deviation_index"] = deviation_index

        # メトリックパッケージング
        sensor_signals = {
            "deviation_index": round(deviation_index, 4),
            "raw_deviation_unfiltered": round(raw_deviation_scaled, 4),
            
            # 3軸個別偏差
            "geom_dev_component": round(float(geom_dev_tensor.mean().item()), 4),
            "time_dev_component": round(float(time_dev_tensor.mean().item()), 4),
            "dens_dev_component": round(float(dens_dev_tensor.mean().item()), 4),
            
            # 各要素
            "dispersion": round(float(geom["dispersions"].mean().item()), 4),
            "major_radius": round(float(geom["major_radius"].mean().item()), 4),
            "minor_radius": round(float(geom["minor_radius"].mean().item()), 4),
            "curvature": round(float(geom["curvature"].mean().item()), 4),
            "degeneracy": round(float(geom["degeneracy"].mean().item()), 4),
            "instant_bpm": round(float(time_ana["instant_bpm"].mean().item()), 4),
            "bpm_variance": round(float(time_ana["bpm_variance"].mean().item()), 4),
            "bpm_entropy": round(float(time_ana["bpm_entropy"].mean().item()), 4),
            "autocorr_lag1": round(float(time_ana["autocorr_lag1"].mean().item()), 4),
            "grid_entropy": round(float(dens["grid_entropy"].mean().item()), 4),
            "attractor_age": int(self.attractor_age.max().item()),
            "norm_attractor_age": round(float(norm_attractor_age.mean().item()), 4), # 正規化アトラクタ寿命
            "dynamic_state_bound": round(self.state_bound, 4)
        }

        return new_axis, new_res, new_ten, sensor_signals

    # ============================================================
    # Ver 4.2 新規：ターミナル・フローレンダラー
    # ============================================================
    def render_flow_matrix(self, channel_idx: int = 0) -> str:
        """
        特定のセンサーチャネルにおけるグリッド間の流動強度（flow_matrix）を、
        アスキーグラフィックスを用いて可視化表現した文字列を返します。
        """
        if channel_idx >= self.num_positions:
            return "Channel out of range."

        # 各ノード内のフロー密度の合算
        matrix = self.flow_matrix[channel_idx]
        max_val = float(matrix.max().item()) + 1e-9
        
        # ターミナル用の表現文字
        chars = [" ", ".", ":", "-", "=", "+", "*", "#", "%", "@"]
        num_chars = len(chars)

        lines = [f"=== CHANNEL {channel_idx} FLOW MATRIX GRID ({self.grid_res}x{self.grid_res}) ==="]
        for r in range(self.grid_res):
            row_str = " | "
            for c in range(self.grid_res):
                # 簡略化のために、あるセルからの「アウトフロー（累積遷移強度の合計）」をプロット
                idx = r * self.grid_res + c
                cell_intensity = float(matrix[idx].sum().item())
                char_idx = min(int((cell_intensity / max_val) * num_chars), num_chars - 1)
                row_str += chars[char_idx] + " "
            row_str += "|"
            lines.append(row_str)
        lines.append("-" * (self.grid_res * 2 + 6))
        return "\n".join(lines)


# ============================================================
# テストシミュレーション・挙動検証
# ============================================================
if __name__ == "__main__":
    print("[SYSTEM] STARTING MOUNTED GRID SPACE OBSERVER (Ver 4.2)...")
    
    # 3チャネルで高速校正動作
    observer = GridSpaceObserver(
        num_positions=3, 
        grid_resolution=4, 
        trajectory_len=16, 
        bpm_history_len=16,
        calibration_steps=3,
        smoothing_alpha=0.40
    )
    
    state = observer.create_initial_state()
    
    for step in range(12):
        theta = step * 0.4
        if step < 5:
            # 安定円
            signal_input = torch.tensor([math.sin(theta), math.sin(theta + 0.2), 0.0])
        elif step < 9:
            # 高強度カオス
            signal_input = torch.tensor([math.sin(theta * 3.0) * 2.5, 0.0, math.cos(theta * 2.5) * 1.5])
        else:
            # 突然の完全静止
            signal_input = torch.tensor([0.0, 0.0, 0.0])
            
        state, metrics = observer.observe_step(state, signal_input, dt=1.0)
        
        print(f"\n[STEP {step:02d}] DEV_IDX (tanh): {metrics.deviation_index:.3f} (RAW_SCALED: {metrics.sensor_signals['raw_deviation_unfiltered']:.3f})")
        sig = metrics.sensor_signals
        print(f"  ├─ ANALYSIS │ 主犯軸 -> GEOM: {sig['geom_dev_component']:.2f} | TIME: {sig['time_dev_component']:.2f} | DENS: {sig['dens_dev_component']:.2f}")
        print(f"  ├─ GEOMETRY │ Major: {sig['major_radius']:.3f} | Minor: {sig['minor_radius']:.3f} | Curv: {sig['curvature']:.3f}")
        print(f"  ├─ TIME     │ BPM: {sig['instant_bpm']:.3f} | Lag1: {sig['autocorr_lag1']:.3f} | B_Bound: {sig['dynamic_state_bound']:.2f}")
        print(f"  └─ DENSITY  │ Grid_Ent: {sig['grid_entropy']:.3f} | Norm_Age: {sig['norm_attractor_age']:.2f} ({sig['attractor_age']} steps)")

    # フロー可視化テスト
    print("\n[SYSTEM] RENDERING FINAL TRANSIENT STATE PATHWAYS:")
    print(observer.render_flow_matrix(channel_idx=0))
