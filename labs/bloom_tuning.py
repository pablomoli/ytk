"""Tune the bloom constants against a real frame before writing any GLSL.

Bloom is four steps — draw to a texture, keep only the bright parts, blur
them, add the blur back — and every one of them is plain arithmetic. So this
notebook is not a model of the effect: it is the same arithmetic on the same
pixels, run over a frame actually captured from the map. Whatever you dial in
here transfers to the shader as literal constants.

Run:  uv run marimo edit labs/bloom_tuning.py
Then: docs/assets/bloom/ gets the checkpoint via `Export figure` at the bottom.
"""

import marimo

__generated_with = "0.23.15"
app = marimo.App(width="medium")


@app.cell
def _():
    from pathlib import Path

    import marimo as mo
    import numpy as np
    from PIL import Image

    REPO = Path(__file__).resolve().parents[1]
    FRAME = REPO / "docs" / "assets" / "flow-pulses" / "05-motion-on-a.png"

    frame = np.asarray(Image.open(FRAME).convert("RGB"), dtype=np.float32) / 255.0
    mo.md(
        f"""
        # Bloom tuning — feature C

        Frame: `{FRAME.relative_to(REPO)}` &nbsp; {frame.shape[1]}×{frame.shape[0]}

        This is a real capture of the map with ribbons (B) and flow pulses (A)
        live. The pipeline below is the same one the shader will run.
        """
    )
    return FRAME, Image, Path, REPO, frame, mo, np


@app.cell
def _(mo):
    threshold = mo.ui.slider(
        0.0, 1.0, 0.02, value=0.34, label="bright-pass threshold", show_value=True
    )
    knee = mo.ui.slider(0.0, 0.5, 0.01, value=0.12, label="knee (soft cutoff)", show_value=True)
    sigma = mo.ui.slider(1.0, 24.0, 0.5, value=7.0, label="blur radius σ (px)", show_value=True)
    passes = mo.ui.slider(1, 4, 1, value=2, label="blur passes (ping-pong)", show_value=True)
    intensity = mo.ui.slider(
        0.0, 3.0, 0.05, value=1.15, label="composite intensity", show_value=True
    )
    downsample = mo.ui.slider(1, 8, 1, value=2, label="downsample factor", show_value=True)

    mo.md(
        f"""
        ## Dials

        {threshold} &nbsp; only pixels brighter than this bloom at all. Too low and
        the whole map hazes over; too high and only the pulse crests glow.

        {knee} &nbsp; how abruptly the threshold bites. 0 is a hard cutoff and
        tends to make bloom pop on and off as the pulse travels.

        {sigma} &nbsp; how far the light spreads.

        {passes} &nbsp; each pass re-blurs the result — cheaper than one huge
        radius and gives a softer falloff.

        {intensity} &nbsp; how much of the blur is added back on top.

        {downsample} &nbsp; blur is done at reduced resolution on the GPU because
        it is the expensive step; this shows what that costs you visually.
        """
    )
    return downsample, intensity, knee, passes, sigma, threshold


@app.cell
def _(np):
    def luma(img):
        return img @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

    def bright_pass(img, threshold, knee):
        """Keep what is brighter than the threshold, with a soft shoulder.

        The knee matters more than it looks: a hard cutoff makes a travelling
        pulse cross the threshold abruptly, so the glow blinks rather than
        swells. Mirrors the smoothstep the fragment shader will use.
        """
        y = luma(img)
        if knee <= 1e-6:
            w = (y > threshold).astype(np.float32)
        else:
            t = np.clip((y - (threshold - knee)) / (2 * knee), 0, 1)
            w = t * t * (3 - 2 * t)
        return img * w[..., None]

    def gaussian_1d(sigma):
        radius = max(1, int(np.ceil(sigma * 3)))
        x = np.arange(-radius, radius + 1, dtype=np.float32)
        k = np.exp(-(x**2) / (2 * sigma**2))
        return k / k.sum()

    def blur_separable(img, sigma, passes):
        """Horizontal then vertical, repeated.

        A true 2D blur has every pixel read a whole neighbourhood. Doing one
        axis at a time gives a visually identical result for a fraction of the
        work, which is why every bloom implementation is two passes bouncing
        between two textures.
        """
        k = gaussian_1d(sigma)
        out = img
        for _ in range(passes):
            out = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 1, out)
            out = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 0, out)
        return out

    def box_down(img, factor):
        if factor <= 1:
            return img
        h = (img.shape[0] // factor) * factor
        w = (img.shape[1] // factor) * factor
        return img[:h, :w].reshape(h // factor, factor, w // factor, factor, 3).mean((1, 3))

    def upsample_to(img, shape):
        fy = shape[0] / img.shape[0]
        fx = shape[1] / img.shape[1]
        yi = np.clip((np.arange(shape[0]) / fy).astype(int), 0, img.shape[0] - 1)
        xi = np.clip((np.arange(shape[1]) / fx).astype(int), 0, img.shape[1] - 1)
        return img[yi][:, xi]

    return (
        blur_separable,
        box_down,
        bright_pass,
        gaussian_1d,
        luma,
        upsample_to,
    )


@app.cell
def _(
    blur_separable,
    box_down,
    bright_pass,
    downsample,
    frame,
    intensity,
    knee,
    np,
    passes,
    sigma,
    threshold,
    upsample_to,
):
    bright = bright_pass(frame, threshold.value, knee.value)
    small = box_down(bright, downsample.value)
    blurred_small = blur_separable(small, sigma.value / max(downsample.value, 1), passes.value)
    blurred = upsample_to(blurred_small, frame.shape[:2])
    composed = np.clip(frame + intensity.value * blurred, 0, 1)

    lit = float((bright.max(axis=2) > 0.01).mean() * 100)
    return blurred, blurred_small, bright, composed, lit, small


@app.cell
def _(Image, np):
    # No leading underscore: marimo scopes underscore-prefixed names to the
    # cell that defines them, so a helper named _png is invisible everywhere
    # else and the notebook fails at the next cell.
    def to_png(arr):
        return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))

    return (to_png,)


@app.cell
def _(lit, mo):
    mo.md(
        f"""
        ## Result

        **{lit:.1f}%** of the frame passes the bright-pass. Under ~1% and the
        bloom is invisible; over ~15% and the map starts to look foggy rather
        than lit.
        """
    )
    return


@app.cell
def _(bright, composed, frame, mo, to_png):
    mo.hstack(
        [
            mo.vstack([mo.md("**before**"), mo.image(to_png(frame), width=520)]),
            mo.vstack([mo.md("**bright-pass**"), mo.image(to_png(bright), width=520)]),
            mo.vstack([mo.md("**after**"), mo.image(to_png(composed), width=520)]),
        ],
        justify="start",
    )
    return


@app.cell
def _(downsample, intensity, knee, mo, passes, sigma, threshold):
    mo.md(
        f"""
        ## Constants for the shader

        Paste these into `mapRenderer.ts` when the look is right:

        ```glsl
        // bright-pass
        const float BLOOM_THRESHOLD = {threshold.value:.2f};
        const float BLOOM_KNEE      = {knee.value:.2f};
        // blur
        const float BLOOM_SIGMA     = {sigma.value:.1f};   // px, at full res
        const int   BLOOM_PASSES    = {passes.value};
        const int   BLOOM_DOWNSAMPLE= {downsample.value};
        // composite
        const float BLOOM_INTENSITY = {intensity.value:.2f};
        ```

        Suggested starting point if you want somewhere to return to:
        threshold 0.34, knee 0.12, σ 7.0, 2 passes, downsample 2, intensity 1.15.
        """
    )
    return


if __name__ == "__main__":
    app.run()
