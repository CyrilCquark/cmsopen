# Structural self-checks: every number stated in the "Production results" text equals results/production.json.
def gev(value, channel, sign=False):
    """A GeV value with the channel's decimals, as in the text."""
    decimals = 4 if channel == "Z_mumu" else 5
    if value is None:
        return "n/a"
    return f"{value:+.{decimals}f}" if sign else f"{value:.{decimals}f}"


def stated_numbers(channel):
    """The text's numbers for one channel, recomputed here from the production file."""
    c = PRODUCTION["channels"][channel]
    r = c["result"]
    numbers = {
        "peak position": gev(r["peak_position_gev"], channel), "raw stat. error": gev(r["stat_error_gev"], channel),
        "scaled stat. error": gev(r["stat_error_scaled_gev"], channel), "scale factor": f"{r['scale_factor']:.3f}",
        "resolution": gev(r["resolution_gev"], channel), "resolution error": gev(r["resolution_error_gev"], channel),
        "chi2": f"{r['chi2']:.1f}", "ndf": str(r["ndf"]), "chi2/ndf": f"{r['chi2_ndf']:.3f}",
        "chi2/ndf benchmark": f"{c['t2']['benchmark']:.1f}", "PDG mass": f"{r['pdg_mass_gev']:.4f}",
        "offset": gev(r["offset_from_pdg_gev"], channel, sign=True), "fit-choice spread": gev(c["fit_choice_spread_gev"], channel),
        "pairs": f"{r['n_pairs_in_fit_range']:,}", "events": f"{r['n_events']:,}",
        "fit range low": f"{r['fit_range_gev'][0]:g}", "fit range high": f"{r['fit_range_gev'][1]:g}",
        "files": str(PRODUCTION["sample"]["n_files"]), "benchmark files": str(PRODUCTION["targets"]["T4"]["benchmark"]["n_files"]),
    }
    return {f"{channel} {name}": value for name, value in numbers.items()}


notebook = json.loads((ROOT / "notebooks" / NOTEBOOK).read_text())
text = "\n".join("".join(cell["source"]) for cell in notebook["cells"] if "production-text" in cell["metadata"].get("tags", []))
stated = {}
for channel in NOTEBOOK_CHANNELS:
    stated.update(stated_numbers(channel))
for name, value in stated.items():
    checks.check(f"the text states the {name} of production.json", value.lstrip("+") in text, value)
visible = re.sub(r"<!--.*?-->", "", re.sub(r"\]\([^)]*\)", "]", text), flags=re.S).replace("Run 2012", "").replace("8 TeV", "")
found = re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])", visible)
known = {value.lstrip("+-") for value in stated.values()}
typed = sorted({n.rstrip(",") for n in found} - known)
checks.check("every number in the text comes from production.json", not typed, ", ".join(typed) or "none other")
for name in NOTEBOOK_FIGURES:
    path = FIGURES / name
    checks.check(f"docs/figures/{name} exists and is listed in production.json",
                 path.exists() and f"docs/figures/{name}" in PRODUCTION["figures"])
