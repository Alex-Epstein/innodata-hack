import sys, math, collections
sys.path.insert(0, sys.argv[1])
import numpy as np, gen
seed=int(sys.argv[2]); area=gen.AREAS[(seed-1)%4]
raw=np.maximum(gen.load_mosaic(area),0); wet=gen.water_mask(raw); sm=gen.blur(raw,float(sys.argv[3]))
rng=np.random.default_rng(seed); s=40075016.686*math.cos(math.radians(gen.global_px_to_lonlat(area['x0']*256+256, area['y0']*256+256)[1]))/(256*2**13)
nx,ny=int(gen.CROP_W/s)+2,int(gen.CROP_H/s)+2
band=[];gap=[];grade=[]
for k in range(30):
    c0=int(rng.integers(4,512-nx-4)); r0=int(rng.integers(4,512-ny-4))
    G=sm[r0:r0+ny,c0:c0+nx][::-1].astype(np.float64)
    levels=list(range(20,int(G.max())+1,20))
    for _ in range(5):
        pts=gen.random_trail(rng,G,s)
        if pts is None: continue
        found,z,seg=gen.crossings_by_sampling(G,s,pts,levels)
        pos=np.array([f[0] for f in found]); 
        if len(pos)<2: continue
        gap+=list(np.diff(pos))
        for a,l,_,_ in found:
            i=int(np.searchsorted(seg,a)); near=np.abs(z-l)<2
            lo=i
            while lo>0 and near[lo-1]: lo-=1
            hi=i
            while hi<len(z)-1 and near[hi+1]: hi+=1
            band.append(hi-lo+1); grade.append(abs(z[min(i+10,len(z)-1)]-z[max(i-10,0)])/20)
band=np.array(band); gap=np.array(gap)
print(f"sigma {sys.argv[3]} n={len(band)} band<=15: {(band<=15).mean():.2f}  gap>=40: {(gap>=40).mean():.2f}  grade median {np.median(grade):.2f}  band pct {np.percentile(band,[10,50,90])}")
