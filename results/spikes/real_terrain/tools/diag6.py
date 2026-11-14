import sys, time
sys.path.insert(0, sys.argv[1]); import gen
gen.AREAS  # noqa
gen.MAX_ATTEMPTS=int(sys.argv[3]); seed=int(sys.argv[2]); st={}; t=time.time()
orig=gen.sample.__defaults__
import numpy as np
# limit attempts by monkeypatching range in a copy: just run and time
r=gen.sample(seed, st); print(seed, "found" if r else "NONE", round(time.time()-t,1), st, r[0]["answer_sampling"] if r else "")
