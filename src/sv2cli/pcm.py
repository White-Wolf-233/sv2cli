def encode(audio,bits):
    import numpy as np
    from .errors import SVError
    if bits not in {16,24}:raise SVError("Use PCM16 or PCM24")
    # Audio is channel-major; WAV is sample-major/interleaved. Transposition
    # can leave a Fortran-contiguous array, so make byte packing explicit.
    pcm=np.clip(audio.T,-1,1-1/(1<<(bits-1)))
    integers=np.rint(pcm*(1<<(bits-1))).astype(np.int32)
    if bits==16:return integers.astype("<i2").tobytes(order="C")
    packed=np.ascontiguousarray(integers,dtype="<i4").view(np.uint8).reshape(-1,4)
    return packed[:,:3].tobytes(order="C")
