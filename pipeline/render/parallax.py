"""Build an FFmpeg filtergraph that drifts scene layers at different rates.

This is what turns a flat still into depth: near layers travel further than
far ones, so the scene has genuine motion parallax rather than a pan across a
picture. It costs one extra input per layer and no per-frame Python.
"""
from __future__ import annotations

from pathlib import Path


def build(
    layers: list[dict], *, width: int, height: int, fps: int,
    rate: float = 0.05, overscan: float = 1.18,
) -> tuple[list[str], str]:
    """Return (ffmpeg input args, filter_complex) for a layered parallax scene.

    `layers` is the manifest from layered.render_layers: each entry needs a
    `path` and a `depth` in 0..1, far to near.
    """
    if not layers:
        raise ValueError("parallax.build called with no layers")

    ow, oh = int(width * overscan), int(height * overscan)
    inputs: list[str] = []
    chains: list[str] = []

    for i, layer in enumerate(layers):
        inputs += ["-loop", "1", "-i", str(layer["path"])]
        depth = float(layer.get("depth", 0.0))
        # Travel scales with depth, so the nearest layer moves most. The
        # vertical component is deliberately smaller — horizontal drift alone
        # reads as a camera move; equal vertical reads as floating.
        span = 0.5 * depth
        vspan = 0.28 * depth
        # Each layer gets its own phase so they never move in lockstep.
        phase = i * 0.7
        x_expr = f"(in_w-out_w)*(0.5+{span:.4f}*sin(t*{rate:.5f}+{phase:.3f}))"
        y_expr = f"(in_h-out_h)*(0.5+{vspan:.4f}*sin(t*{rate * 0.63:.5f}+{phase:.3f}))"
        chains.append(
            f"[{i}:v]scale={ow}:{oh},crop={width}:{height}:x='{x_expr}':y='{y_expr}',"
            f"format=rgba[l{i}]"
        )

    # Stack the layers back to front.
    merges = []
    current = "l0"
    for i in range(1, len(layers)):
        out = f"m{i}"
        merges.append(f"[{current}][l{i}]overlay=0:0:format=auto[{out}]")
        current = out

    tail = f"[{current}]fps={fps},format=yuv420p[v]"
    filter_complex = ";".join(chains + merges + [tail])
    return inputs, filter_complex
