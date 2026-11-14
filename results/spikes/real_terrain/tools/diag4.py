import sys, time, math, collections
sys.path.insert(0, sys.argv[1])
import numpy as np, gen
seed = int(sys.argv[2]); area = gen.AREAS[(seed-1) % 4]
t=time.time(); raw=np.maximum(gen.load_mosaic(area),0); wet=gen.water_mask(raw); sm=gen.blur(raw,1.0); print("load", round(time.time()-t,2))
rng=np.random.default_rng(seed); s=40075016.686*math.cos(math.radians(gen.global_px_to_lonlat(area['x0']*256+256, area['y0']*256+256)[1]))/(256*2**13)
nx,ny=int(gen.CROP_W/s)+2,int(gen.CROP_H/s)+2
C=collections.Counter(); ns=[]; MR=[]; slopes=[]
t=time.time()
for k in range(40):
    c0=int(rng.integers(4,512-nx-4)); r0=int(rng.integers(4,512-ny-4))
    G=sm[r0:r0+ny,c0:c0+nx][::-1].astype(np.float64); Wt=wet[r0:r0+ny,c0:c0+nx][::-1]
    ci=20
    levels=[l for l in range(int(math.ceil(max(G.min(),.5)/ci))*ci,int(G.max())+1,ci) if l>0]
    for _ in range(10):
        pts=gen.random_trail(rng,G,s)
        if pts is None: C['notrail']+=1; continue
        q=gen.densify(pts,5.0); jj,ii=np.round(q[:,0]/s).astype(int),np.round(q[:,1]/s).astype(int)
        if Wt[np.clip(ii,0,ny-1),np.clip(jj,0,nx-1)].any(): C['water']+=1; continue
        found,z,seg=gen.crossings_by_sampling(G,s,pts,levels); n=len(found); ns.append(n)
        if not 8<=n<=20: C['count']+=1; continue
        pos=np.array([f[0] for f in found]); L=seg[-1]
        if pos.min()<40 or pos.max()>L-40 or (np.diff(pos)<40).any(): C['sep']+=1; continue
        runs=[]
        for l in levels:
            near=np.abs(z-l)<2
            if near.any():
                e=np.diff(np.r_[0,near.astype(int),0]); runs.append((np.where(e==-1)[0]-np.where(e==1)[0]).max())
        MR.append(max(runs)); slopes.append(np.median(np.abs(np.diff(z))))
        
        for RUN in (15,30,45,60):
            if not gen.grazes(z,levels,RUN): C[f'pass_graze{RUN}']+=1
        p1=gen.densify(pts,1.0)
        
        r=gen.unfair(G,s,p1,z,found,levels,ci) if not gen.grazes(z,levels,15) else None
        r=gen.unfair(G,s,p1,z,found,levels,ci)
        if r: C[r]+=1; continue
        C['ok']+=1
print(C, "time", round(time.time()-t,1), "n pct", np.percentile(ns,[10,50,90]) if ns else None)

print('maxrun pct', np.percentile(MR,[0,10,50]) if MR else None, 'median along-trail slope', np.median(slopes) if slopes else None)
