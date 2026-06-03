from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageFilter


def smooth_alpha(alpha: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return alpha
    image = Image.fromarray(alpha.astype(np.uint8), mode="L")
    return np.asarray(image.filter(ImageFilter.GaussianBlur(radius=float(radius))))


def contract_alpha(alpha: np.ndarray, amount: float, *, threshold: int = 16, feather: float = 0.0) -> np.ndarray:
    pixels = max(0.0, float(amount))
    feather_radius = max(0.0, float(feather))
    if pixels <= 0 and feather_radius <= 0:
        return alpha

    source_alpha = np.clip(alpha, 0, 255).astype(np.uint8)
    safe_threshold = int(np.clip(threshold, 0, 255))
    binary_mask = source_alpha >= safe_threshold
    if not np.any(binary_mask):
        return source_alpha

    edge_distance = _edge_distance(binary_mask)
    if feather_radius <= 0:
        weight = edge_distance > pixels
    else:
        ramp = np.clip((edge_distance - pixels) / feather_radius, 0, 1)
        weight = ramp * ramp * (3 - 2 * ramp)
    # 先按阈值找到素材真实边界，再按距离场做软收缩。
    # 距离场比逐圈腐蚀更接近连续边界，斜线和弧线在放大后不容易出现明显台阶。
    return np.clip(source_alpha.astype(np.float32) * weight, 0, 255).astype(np.uint8)


def decontaminate_edge_colors(source: Image.Image, alpha: np.ndarray, radius: int, *, threshold: int = 16) -> Image.Image:
    pixels = max(0, int(radius))
    if pixels <= 0:
        return apply_alpha(source, alpha)

    source_alpha = np.clip(alpha, 0, 255).astype(np.uint8)
    binary_mask = source_alpha >= int(np.clip(threshold, 0, 255))
    if not np.any(binary_mask):
        return apply_alpha(source, source_alpha)

    edge_distance = _edge_distance(binary_mask)
    edge_band = (source_alpha > 0) & (edge_distance > 0) & (edge_distance <= pixels + 1)
    filled = (source_alpha >= max(96, threshold)) & (edge_distance > pixels + 1)
    if not np.any(edge_band) or not np.any(filled):
        return apply_alpha(source, source_alpha)

    rgb = np.asarray(source.convert("RGB"), dtype=np.float32).copy()
    kernel = np.ones((3, 3), dtype=np.float32)
    target = edge_band.copy()
    filled_mask = filled.astype(np.float32)
    for _ in range(pixels + 2):
        neighbor_count = cv2.filter2D(filled_mask, -1, kernel, borderType=cv2.BORDER_CONSTANT)
        fillable = target & (filled_mask <= 0) & (neighbor_count > 0)
        if not np.any(fillable):
            break
        for channel in range(3):
            neighbor_sum = cv2.filter2D(rgb[:, :, channel] * filled_mask, -1, kernel, borderType=cv2.BORDER_CONSTANT)
            rgb[:, :, channel][fillable] = neighbor_sum[fillable] / neighbor_count[fillable]
        filled_mask[fillable] = 1

    # 去边色只替换透明边缘的 RGB，alpha 仍沿用前面的收缩结果。
    # PNG 的半透明边如果保留旧背景色，导入游戏引擎后会在深色背景上露出浅边。
    result = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), mode="RGB").convert("RGBA")
    result.putalpha(Image.fromarray(source_alpha, mode="L"))
    return result


def apply_alpha(source: Image.Image, alpha: np.ndarray) -> Image.Image:
    rgba = source.convert("RGBA")
    alpha_image = Image.fromarray(np.clip(alpha, 0, 255).astype(np.uint8), mode="L")
    rgba.putalpha(alpha_image)
    return rgba


def connected_components(alpha: np.ndarray, *, threshold: int, min_area: int) -> list[tuple[int, tuple[int, int, int, int], int, np.ndarray]]:
    binary_mask = (alpha >= threshold).astype(np.uint8)
    label_count, labels, stats, _ = cv2.connectedComponentsWithStats(binary_mask, connectivity=8)
    components: list[tuple[int, tuple[int, int, int, int], int, np.ndarray]] = []
    for label_index in range(1, label_count):
        x, y, width, height, area = stats[label_index]
        if int(area) < min_area:
            continue
        component_binary = labels == label_index
        component_alpha = np.where(component_binary, alpha, 0).astype(np.uint8)
        components.append((label_index, (int(x), int(y), int(width), int(height)), int(area), component_alpha))
    components.sort(key=lambda item: (item[1][1], item[1][0]))
    return components


def _edge_distance(binary_mask: np.ndarray) -> np.ndarray:
    padded_mask = np.pad(binary_mask.astype(np.uint8), 1, mode="constant", constant_values=0)
    distance = cv2.distanceTransform(padded_mask, cv2.DIST_L2, 3).astype(np.float32)
    return distance[1:-1, 1:-1]
