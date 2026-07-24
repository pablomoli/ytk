# Density terrain: the derivations behind `ytk/ridges.py`

Companion note to the /map terrain overlay (session 033). Everything here is
implemented from scratch in `ytk/ridges.py` and verified against finite
differences in `tests/test_ridges.py`. Course anchors: MAC 2313 (gradients,
level sets, directional derivatives), MAS 3105 (symmetric matrices, spectral
theorem, eigendecomposition), STA 2023 (density estimation).

## 1. The density field (KDE)

The 2D map layout is a point set x_1..x_n in the plane. The kernel density
estimate places an isotropic Gaussian bump on every point:

    f(x) = (1/n) sum_i K_h(x - x_i),
    K_h(u) = exp(-|u|^2 / 2h^2) / (2 pi h^2)

Bandwidth h is Silverman's 2D rule of thumb, h = sigma * n^(-1/6) with sigma
the per-axis standard deviation averaged. Larger n -> narrower bumps, because
more data supports finer structure.

## 2. Gradient of log f — the mean-shift identity

Work with g(x) = sum_i w_i(x), where w_i = exp(-|x - x_i|^2 / 2h^2), so
log f = log g + const. Each kernel differentiates to

    grad w_i = w_i * (x_i - x) / h^2        (chain rule on -|x - x_i|^2/2h^2)

Summing and dividing by g:

    grad log f = grad g / g = (1/h^2) * [ sum_i w_i x_i / sum_i w_i  -  x ]
               = m(x) / h^2

The bracket m(x) is the *mean-shift vector*: the weighted average of the data
points near x, minus x itself. Steepest ascent on the log-landscape literally
means "step toward the local center of mass." This identity is why mean-shift
iterations need no step-size tuning — h^2 * grad log f IS the natural step.

## 3. Hessian of log f

Differentiate grad g once more (product rule; d_i = x_i - x):

    hess g = sum_i [ w_i d_i d_i^T / h^4  -  w_i I / h^2 ]

and use hess log g = hess g / g - (grad g / g)(grad g / g)^T:

    hess log f = (S - m m^T) / h^4  -  I / h^2,
    S = sum_i w_i d_i d_i^T / sum_i w_i

S - m m^T is exactly the *weighted local covariance* of the data around x —
the Hessian of the log-density is (covariance/h^2 - I)/h^2. Where the local
cloud is wide (variance > h^2 in some direction) the log-density curves up;
where it is narrow it curves down. Both formulas are checked against central
finite differences at 1e-4 relative tolerance.

## 4. Eigenstructure: the spectral theorem does the work

The Hessian is symmetric, so (MAS 3105, spectral theorem) it has two real
eigenvalues lambda_1 >= lambda_2 with orthogonal eigenvectors v_1, v_2. On a
crest, the ground falls away steeply *across* the ridge (lambda_2 strongly
negative, direction v_2) and is nearly flat *along* it (lambda_1 ~ 0,
direction v_1). Closed form for [[a, b], [b, c]]:

    lambda = (a + c)/2 +- sqrt( ((a - c)/2)^2 + b^2 )

with eigenvector candidates (b, lambda - a) and (lambda - c, b) from
(A - lambda I)v = 0; the second eigenvector is the 90-degree rotation of the
first (orthogonality is free for symmetric matrices).

## 5. The ridge set and SCMS

Definition (Ozertem & Erdogmus 2011): x is on a 1D ridge iff

    v_2^T grad f(x) = 0   and   lambda_2(x) < 0

— a local maximum in the cross-ridge direction, regardless of what happens
along the crest. Plain mean shift follows the full gradient and lands on
modes (peaks). Subspace-constrained mean shift instead projects each step
onto v_2 only:

    x <- x + (v_2 v_2^T) m(x)

deleting the along-ridge component, so walkers climb sideways onto the crest
and stop exactly where the ridge condition holds. Convergence is declared
when the projected step is below 1e-4; walkers whose density falls below 5%
of the peak are discarded (they were climbing noise). Converged walkers are
thinned into ~0.01 cells (averaging within each cell) and chained by greedy
nearest-neighbor linking into polylines.

## 6. Contours (marching squares)

Level sets {f = c} at fixed fractions of the density peak. For each grid
cell, classify the four corners as above/below c (16 cases), place vertices
on crossing edges by linear interpolation, and connect according to the case
table; the two saddle cases are disambiguated by the cell-center value.
Segments are chained into polylines by endpoint matching. Verified on an
isotropic Gaussian, whose level set must be a circle of radius
h * sqrt(2 ln 2) at half-peak.

## 7. Why terrain instead of clusters

The embedding-map postmortems concluded this space has *gradients, not
clusters*: no reproducible flat partition exists, but the coarse geometry
reproduces. Contours and ridges render exactly that structure without
inventing boundaries — the connective tissue between regions is a ridge you
can see, and the absence of a valley between two "clusters" is honest
evidence they were never separate.

## 8. One dimension up: the filament web (session 034)

Everything above survives promotion to the 3D embedding volume unchanged:
the KDE normalization becomes (2 pi h^2)^(3/2), Silverman's exponent
n^(-1/7), and the gradient/Hessian derivations never mentioned dimension
(the code is now dimension-agnostic and the same finite-difference tests
pass in both).

What changes is the eigenstructure. The Hessian is symmetric 3x3, so the
spectral theorem yields THREE orthogonal directions. On a filament (1D
ridge in 3D): two strongly negative curvatures (the cross-sectional disk)
and one mild one (along the wire). The ridge condition gains a second
equation:

    v2^T grad f = 0  AND  v3^T grad f = 0,   lambda2, lambda3 < 0

SCMS projects each mean-shift step onto span{v2, v3} — equivalently, onto
the orthogonal complement of v1 (the top eigenvector):

    step = m(x) - (v1 . m(x)) v1

Using the complement of the single top eigenvector sidesteps the
degeneracy of separating v2 from v3 when the cross-disk curvatures are
nearly equal (their individual directions are unstable but their span is
not).

Closed-form eigenvalues of a symmetric 3x3 require solving a cubic —
enter Cardano: shift by the trace mean (q = tr/3), scale by the Frobenius
spread, and the characteristic polynomial collapses to 4c^3 - 3c = det(B),
which is the triple-angle identity for cosine; the three roots are three
cosines at 120-degree offsets. Verified against np.linalg.eigh including
diagonal and isotropic branches. The top eigenvector comes from cross
products of rows of (A - lambda I): every row is orthogonal to v, so any
two independent rows' cross product IS v (pick the largest-norm pair for
stability).

Filament vertices carry a kernel-weighted majority label (domain/theme) —
the same weights w_i that build the density also interpolate the topic
colors, so one field serves both geometry and paint.

## 9. Adaptive bandwidth (session 036-037)

Sample-point adaptive KDE: each point casts a bump of its own width
h_i (k-NN-scaled, median-anchored to Silverman, clamped). Every kernel
now carries its own normalization c_i = (2 pi h_i^2)^(-d/2), so with
w_i = c_i exp(-|d_i|^2/2h_i^2) and the "pull weights" u_i = w_i/h_i^2:

    grad log f = sum u_i d_i / sum w_i
    hess log f = sum (w_i/h_i^4) d_i d_i^T / sum w_i
                 - (sum u_i / sum w_i) I - (grad)(grad)^T

Uniform h collapses these to the section-2/3 forms (checked by test).
The natural mean-shift step size becomes W/U = sum w_i / sum u_i — a
density-weighted harmonic-mean h^2 (Comaniciu's variable-bandwidth mean
shift) — instead of the constant h^2.

**The scale-space lesson (measured, not asserted).** Adaptivity sharpens
peaks, which is what the fog wants (local thickness, more resolved
cores) and exactly what ridge tracing does NOT want: on the sharper
density the long connective crest through the epicmap mass fragmented
from an 89-vertex chain into ~30-vertex dashes, and milder clamps did
not recover it. The estimator must match the question: fog = adaptive,
web = uniform. Record: docs/assets/fog/04-filaments-uniform-vs-adaptive.png.

**Display normalization is part of the transfer function.** Two failed
normalizations preceded the working one (against max point density, then
against a percentile of POINT densities — points sit on peaks, samples
hover off-peak, everything compressed to darkness). Correct reference
population: the splats actually displayed, scaled to their own 99th
percentile. The matplotlib witness (scripts/plot_fog.py) caught both
failures before anything shipped.

## Failure modes worth remembering

- A sign error in the Hessian sends SCMS walkers off the data (they seek
  valleys); the visual is unmistakable scribble.
- Chaining ridge points with a link radius derived from median NN distance
  fails when walkers bunch unevenly along the crest — thin to a uniform cell
  size first (0.01 in layout units), then chain.
- Whitening/mean-centering intuitions from the embedding space do NOT apply
  here: terrain is computed in the 2D layout space, which UMAP has already
  made roughly isotropic.
