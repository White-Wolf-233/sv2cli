"""BS.1770-4 integrated loudness (LUFS) and approximate true peak.

Requires numpy. scipy is used for biquad filtering when available;
falls back to a Python loop that is slower but correct.
"""
import math

def _numpy():
    try:
        import numpy as np
        return np
    except ImportError:
        from .errors import SVError
        raise SVError("Install audio analysis: pip install 'sv2cli[audio]'", 'missing_dependency')

def _kweight_coeffs(stage, fs):
    """Return (b, a) biquad coefficients for K-weighting stage 1 or 2 (BS.1770-4)."""
    if stage == 1:
        f0 = 1681.974450955533
        G  = 3.999843853973347
        Q  = 0.7071752369554196
        K  = math.tan(math.pi * f0 / fs)
        Vh = 10 ** (G / 20.0)
        Vb = Vh ** 0.4845
        a0 = 1 + K / Q + K * K
        b0 = (Vh + Vb * K / Q + K * K) / a0
        b1 = 2.0 * (K * K - Vh) / a0
        b2 = (Vh - Vb * K / Q + K * K) / a0
        a1 = 2.0 * (K * K - 1) / a0
        a2 = (1 - K / Q + K * K) / a0
    else:  # stage 2
        f0 = 38.13547087602444
        Q  = 0.5003270373238773
        K  = math.tan(math.pi * f0 / fs)
        a0 = 1 + K / Q + K * K
        b0 = 1.0
        b1 = -2.0
        b2 = 1.0
        a1 = 2.0 * (K * K - 1) / a0
        a2 = (1 - K / Q + K * K) / a0
    return (b0, b1, b2), (1.0, a1, a2)

def _biquad(x, b, a):
    """Apply 2nd-order IIR (direct form II transposed). scipy if available, else Python loop."""
    try:
        from scipy.signal import lfilter
        return lfilter(b, a, x)
    except ImportError:
        pass
    np = _numpy()
    b0, b1, b2 = float(b[0]), float(b[1]), float(b[2])
    a1, a2 = float(a[1]), float(a[2])
    y = np.empty(len(x), dtype=np.float64)
    w1 = w2 = 0.0
    for i, xi in enumerate(x):
        xi = float(xi)
        yi = b0 * xi + w1
        w1 = b1 * xi - a1 * yi + w2
        w2 = b2 * xi - a2 * yi
        y[i] = yi
    return y

def _kweighted(audio, rate):
    """Return K-weighted sum-of-squares signal (shape: samples)."""
    np = _numpy()
    b1, a1 = _kweight_coeffs(1, rate)
    b2, a2 = _kweight_coeffs(2, rate)
    z = np.zeros(audio.shape[1], dtype=np.float64)
    for ch in range(audio.shape[0]):
        s = audio[ch].astype(np.float64)
        s = _biquad(s, b1, a1)
        s = _biquad(s, b2, a2)
        z += s * s
    return z

def integrated_lufs(audio, rate):
    """
    BS.1770-4 integrated loudness.
    audio: ndarray shape (channels, samples), normalized [-1, 1].
    Returns float LUFS or None if insufficient audio.
    """
    np = _numpy()
    n = audio.shape[1]
    if n == 0:
        return None
    z = _kweighted(audio, rate)

    block = int(0.4 * rate)
    hop   = int(0.1 * rate)
    if n < block:
        return None

    # Compute per-block mean square
    means = []
    start = 0
    while start + block <= n:
        means.append(float(np.mean(z[start:start + block])))
        start += hop
    if not means:
        return None
    means = np.array(means)

    # Absolute gate: -70 LUFS
    abs_thresh = 10 ** ((-70 + 0.691) / 10)
    gated = means[means >= abs_thresh]
    if gated.size == 0:
        return None

    # Relative gate: gated mean - 10 LU
    rel_thresh = float(np.mean(gated)) * 10 ** (-10 / 10)
    final = gated[gated >= rel_thresh]
    if final.size == 0:
        return None

    return float(-0.691 + 10 * math.log10(float(np.mean(final))))

def shortterm_lufs_bins(audio, rate):
    """
    3-second short-term LUFS, one value per second (hop = 1 s).
    Returns list of dicts {second, lufs} for seconds with valid signal.
    """
    np = _numpy()
    n = audio.shape[1]
    if n == 0:
        return []
    z = _kweighted(audio, rate)
    block = int(3.0 * rate)
    hop   = rate
    if n < block:
        block = n
    bins = []
    sec = 0
    start = 0
    while start + block <= n:
        m = float(np.mean(z[start:start + block]))
        lufs = round(-0.691 + 10 * math.log10(m), 1) if m > 1e-30 else None
        if lufs is not None:
            bins.append({'second': sec, 'lufs': lufs})
        start += hop
        sec += 1
    return bins

def true_peak_dbfs(audio):
    """
    Estimate true peak with a 4x, 129-tap windowed-sinc reconstruction filter.
    Returns dBTP or None for silent audio.
    Includes the filter tails and every original sample, including the final one.
    """
    np = _numpy()
    if audio.shape[1] == 0:
        return None
    offsets = np.arange(-64, 65, dtype=np.float64)
    kernel = np.sinc(offsets / 4.0) * np.kaiser(len(offsets), 8.6)
    peak = 0.0
    for ch in range(audio.shape[0]):
        x = audio[ch].astype(np.float64)
        for phase in range(4):
            reconstructed = np.convolve(x, kernel[phase::4], mode='full')
            peak = max(peak, float(np.max(np.abs(reconstructed))))
    if peak < 1e-12:
        return None
    return round(20 * math.log10(peak), 2)
