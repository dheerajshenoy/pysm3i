# Core: a model browser and reference

- [ ] Model catalog: List every preset (s1–s7, d0–d12, f1, a1/a2, c1–c4, co1–co3, cib1, tsz1, ksz1, rg1, sz, and so on) grouped by component. Each entry gets a plain-language description, the paper reference, the parametrization, and which templates or maps it uses.
- [ ] Equation view: Render the SED with LaTeX or MathJax, for example the power law for synchrotron and the modified blackbody for dust. Highlight which parameters each preset makes constant, spatially varying, or curved.
- Model comparison: Put d1 and d10 (or s1 and s5) side by side and show what differs, in both the parametrization and the resulting maps.

# Interactive visualization

- Sky maps: Show I/Q/U in Mollweide, Cartesian, and Orthographic projections, with a frequency slider that updates live. Use healpy or matplotlib for a quick first version. pyqtgraph, vispy, or a pyvista sphere give smoother interaction.
- SED explorer: Click a pixel on the sky and plot its emission versus frequency for each component and the total. Overlay the CMB blackbody and mark the frequency bands of instruments such as Planck, LiteBIRD, Simons Observatory, and CMB-S4.
- Component toggles: Turn synchrotron, dust, free-free, AME, and CMB on and off, or stack them. Show the fraction of total power each component contributes at the chosen frequency.
- Parameter playground: Sliders for the spectral index β, dust temperature, and so on, with the SED and map updating live. Because changing a parameter shows its effect directly, this is likely the most useful feature for learning.

# Learning-oriented extras

- Power spectra: Compute and plot C_ℓ (EE, BB, TT) per component and frequency, with a comparison against the CMB signal and an r = 0.01 line. This shows why foregrounds matter for B-mode searches.
- Spatial variation of parameters: Show the β_s and T_d maps themselves.
- Frequency-decorrelation demo: Plot the correlation between maps at two frequencies, which is what models like d10 and s5 are about.
- Unit converter: Convert between K_CMB, K_RJ, and MJy/sr, since unit confusion is a common stumbling block. Show the conversion factors per frequency.
- Guided tour: Short notes such as "what happens to dust at 30 GHz vs 353 GHz" tied to presets of the sliders.

# Practical features

- Simulation builder: Choose a preset combination, add bandpass and beam settings, and export FITS maps or a ready-to-run Python snippet using pysm3.Sky(...).
- Bandpass and beam support: Use pysm3.Sky with bandpass_unit, and offer simple Gaussian beam smoothing.
- Resolution control: nside of 32–128 for fast interaction, with an option for full resolution as a background job.

# Technical suggestions

- GUI toolkit: PySide6 or PyQt6 with matplotlib embedded is the easiest start. You mentioned Python only, so I'm suggesting Qt. A web option such as Panel or Streamlit is quicker to build but less snappy for maps.
- Speed: Keep an interactive nside low, cache the template maps, and recompute on a worker thread so sliders don't freeze.
- Structure: A models/ metadata registry (description, references, parameters) separate from the GUI, so adding a model is just adding data.
- Testing: Compare your live results against direct pysm3 output as a regression test.

# Suggested build order

1. Model catalog with descriptions (static, no computation).
2. Single-frequency map viewer with a frequency slider.
3. Pixel-click SED plot.
4. Parameter sliders.
5. Power spectra and export.

