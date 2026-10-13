"""Synthesis readiness based on energy, not nondeterministic sample phase."""
def envelope(audio,sample_rate):
    import numpy as np
    hop=max(1,round(sample_rate*.25))
    mono_energy=np.mean(audio.astype(np.float64)**2,axis=0)
    return np.array([np.sqrt(np.mean(mono_energy[i:i+hop])) for i in range(0,len(mono_energy),hop)])

def convergence(previous,current):
    import numpy as np
    if previous is None or previous.shape!=current.shape:return None
    return float(np.mean((previous-current)**2)/(np.mean(current**2)+1e-16))

def missing_windows(audio,sample_rate,windows,min_peak=1e-6):
    import numpy as np
    missing=[]
    for begin,end in windows:
        lo=max(0,round(begin*sample_rate));hi=min(audio.shape[1],round(end*sample_rate))
        if hi<=lo:continue
        if float(np.max(np.abs(audio[:,lo:hi])))<min_peak:missing.append([begin,end])
    return missing
