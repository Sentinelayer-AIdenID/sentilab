#!/usr/bin/env python3
"""SYNTHETIC educational chiplet thermal placement experiment.

Not silicon, GPU, CFD or foundry signoff. No Jev or other LLM is called.
Steady 2-D finite-volume plate: -k*t*laplacian(T) + h*(T-Tcool) = q''.
All four plate edges are adiabatic. Each cell has vertical cooling to a
uniform isothermal reservoir; exact rectangle/cell overlaps conserve power.
No package stack, temperature-dependent materials, electrical/timing/routing
constraints, convection flow, or junction/plate interface resistance is modeled.
"""
from pathlib import Path
import json, time, platform, math, os
import numpy as np
import scipy
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import factorized
from scipy.stats import spearmanr
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
import sklearn
from threadpoolctl import __version__ as threadpoolctl_version, threadpool_info
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT=Path(__file__).resolve().parent
L=0.025                         # m; square spreading plate
K=120.0                         # W/(m K); constant effective conductivity
THICK=0.0008                    # m; effective spreading layer
H=3000.0                        # W/(m^2 K); effective vertical conductance
TCOOL=25.0                      # degree C, fixed reservoir
SIZES=np.array([[6,6],[6,6],[5,5],[5,5]],float) # mm, fixed footprint
POWERS=np.array([[18,16,8,6],[8,10,17,19]],float) # W/chiplet
UNSEEN_POWER=np.array([[12,12,12,12]],float)
GAP=0.5                        # mm; geometry constraint, not manufacturing rule
BASE_N=40
TRAIN=120
ADDITIONAL=72
TEST=80
SEEDS=[11,29,47]
INITIAL=np.array([[8.,8.],[14.5,8.],[8.,14.5],[14.,14.5]])
START=time.perf_counter()

class Plate:
    def __init__(self,n=40):
        self.n=n; self.dx=L/n; self.cell_area=self.dx**2
        A=lil_matrix((n*n,n*n))
        lateral=K*THICK # equal dx/dy => k*t*dy/dx
        vertical=H*self.cell_area
        for y in range(n):
            for x in range(n):
                z=y*n+x; A[z,z]=vertical
                for xx,yy in [(x-1,y),(x+1,y),(x,y-1),(x,y+1)]:
                    if 0<=xx<n and 0<=yy<n:
                        A[z,z]+=lateral; A[z,yy*n+xx]=-lateral
        self.A=A.tocsc(); self.solve=factorized(self.A)
        self.edges=np.linspace(0,L,n+1)
        self.calls=0; self.seconds=0.
    def source_weights(self,xy):
        cols=[]
        for (cx,cy),(sx,sy) in zip(xy/1000,SIZES/1000):
            ox=np.maximum(0,np.minimum(self.edges[1:],cx+sx/2)-np.maximum(self.edges[:-1],cx-sx/2))
            oy=np.maximum(0,np.minimum(self.edges[1:],cy+sy/2)-np.maximum(self.edges[:-1],cy-sy/2))
            cols.append(np.outer(oy,ox).ravel()/(sx*sy))
        return np.array(cols).T
    def evaluate(self,xy,powers=POWERS,grids=False):
        if not legal(xy):
            raise ValueError('Expected finite 4x2 chiplet centers obeying the plate bounds and axis-separation gap')
        xy=np.asarray(xy,dtype=float)
        powers=np.asarray(powers,dtype=float)
        if powers.ndim!=2 or powers.shape[1]!=4 or powers.shape[0]<1 or not np.all(np.isfinite(powers)) or np.any(powers<0):
            raise ValueError('Expected a finite nonnegative workload-by-4 power array in watts')
        begin=time.perf_counter(); B=self.source_weights(xy)@powers.T
        rise=self.solve(B)
        self.calls+=1; self.seconds+=time.perf_counter()-begin
        temps=TCOOL+rise
        peaks=temps.max(axis=0)
        if grids: return peaks,temps.T.reshape(-1,self.n,self.n),B
        return peaks


def legal(xy):
    """Fixed-size plate placement with a conservative axis-aligned gap.

    For every pair, at least one coordinate axis must separate the footprint
    edges by GAP. This is stricter than general Euclidean corner clearance.
    """
    try:
        xy=np.asarray(xy,dtype=float)
    except (TypeError,ValueError,OverflowError):
        return False
    if xy.shape!=(4,2) or not np.all(np.isfinite(xy)):
        return False
    half=SIZES/2
    if np.any(xy-half < -1e-9) or np.any(xy+half > 25+1e-9):return False
    for i in range(4):
        for j in range(i):
            if np.all(np.abs(xy[i]-xy[j]) < half[i]+half[j]+GAP-1e-9):return False
    return True

def sample(rng):
    # Rejection sampling on a 0.5 mm placement grid. No stochastic physics.
    for _ in range(20000):
        xy=np.array([[rng.integers(int(s[0]),int(50-s[0])+1)/2,
                       rng.integers(int(s[1]),int(50-s[1])+1)/2] for s in SIZES])
        if legal(xy):return xy
    raise RuntimeError('Geometry sampler exhausted')

def mutate(xy,rng,scale=1.5):
    for _ in range(100):
        candidate=xy.copy(); i=rng.integers(4)
        candidate[i]=np.round((candidate[i]+rng.normal(0,scale,2))*2)/2
        if legal(candidate) and not np.array_equal(candidate,xy):return candidate
    return sample(rng)

def features(xy):
    x=xy/25
    # Explicit symmetry and interactions aid a small-data surrogate.
    f=list(x.ravel())+list(np.minimum(x,1-x).ravel())
    for i in range(4):
        for j in range(i):
            d=np.abs(x[i]-x[j]); f.extend([d[0],d[1],float(np.linalg.norm(d))])
    return np.array(f)

def fit_surrogate(layouts,values,seed):
    return ExtraTreesRegressor(n_estimators=120,min_samples_leaf=2,
        random_state=seed,n_jobs=1).fit(np.array([features(x) for x in layouts]),values)

def record(hist,xy,temps,best,origin):
    obj=float(max(temps)); newbest=min(best,obj)
    hist.append({'evaluation':len(hist)+1,'origin':origin,'positions_mm':xy.tolist(),
                 'workload_peak_C':np.asarray(temps).tolist(),'objective_C':obj,'best_so_far_C':newbest})
    return newbest

def optimize(seed,method,initial_layouts,initial_values,model):
    rng=np.random.default_rng(seed+{'random':1000,'local_annealing':2000,'surrogate_screened':3000}[method])
    plate=Plate(BASE_N); hist=[]; best=1e9
    for xy,val in zip(initial_layouts,initial_values):best=record(hist,xy,val,best,'common_initial_design')
    index=int(np.argmin(np.max(initial_values,axis=1)))
    bestxy=initial_layouts[index].copy(); current=bestxy.copy(); currscore=best
    fit_seconds=0.;screen_seconds=0.;screened=0
    layouts=[x.copy() for x in initial_layouts];values=[v.copy() for v in initial_values]
    seen={tuple(x.ravel()) for x in layouts}; mdl=model
    begin=time.perf_counter()
    for j in range(ADDITIONAL):
        if method=='random':candidate=sample(rng)
        elif method=='local_annealing':
            candidate=mutate(current,rng,scale=3*(1-j/ADDITIONAL)+.5)
        else:
            # Independent candidate proposing is ordinary numerical mutation,
            # not language-model output. Rescore global and local alternatives.
            t=time.perf_counter()
            candidates=[mutate(bestxy,rng,scale=rng.choice([.75,1.5,3.])) for _ in range(80)]
            candidates += [sample(rng) for _ in range(48)]
            candidates=[x for x in candidates if tuple(x.ravel()) not in seen]
            if not candidates:candidates=[sample(rng)]
            pred=np.max(mdl.predict(np.array([features(x) for x in candidates])),axis=1)
            candidate=candidates[int(np.argmin(pred))];screened+=len(candidates)
            screen_seconds+=time.perf_counter()-t
        while tuple(candidate.ravel()) in seen:candidate=sample(rng)
        seen.add(tuple(candidate.ravel()))
        val=plate.evaluate(candidate);score=float(max(val));priorbest=best
        best=record(hist,candidate,val,best,method)
        if score<priorbest:bestxy=candidate.copy()
        if method=='local_annealing':
            temperature=max(.10,1.5*(1-j/ADDITIONAL))
            if score<currscore or rng.random()<math.exp(min(0,(currscore-score)/temperature)):
                current=candidate.copy();currscore=score
        layouts.append(candidate.copy());values.append(val.copy())
        if method=='surrogate_screened' and (j+1)%12==0 and j+1<ADDITIONAL:
            t=time.perf_counter();mdl=fit_surrogate(layouts,values,seed);fit_seconds+=time.perf_counter()-t
    peaks,grids,_=plate.evaluate(bestxy,grids=True)
    final_verification_calls=1
    return {'seed':seed,'method':method,'total_search_simulator_calls':TRAIN+ADDITIONAL,
      'additional_search_calls':ADDITIONAL,'final_verification_calls':final_verification_calls,
      'common_initial_best_C':float(np.min(np.max(initial_values,axis=1))),
      'best_objective_C':float(max(peaks)),'best_workload_peak_C':peaks.tolist(),
      'best_positions_mm':bestxy.tolist(),'best_grids_C':grids.tolist(),
      'history':hist,'additional_stage_wall_seconds':time.perf_counter()-begin,
      'additional_simulator_wall_seconds':plate.seconds,
      'surrogate_refit_seconds':fit_seconds,'screening_wall_seconds':screen_seconds,
      'screened_candidates':screened}


def validate_model():
    plate=Plate(BASE_N)
    peaks,grids,B=plate.evaluate(INITIAL,grids=True)
    assert legal(INITIAL)
    rise=grids-TCOOL
    energy_out=H*plate.cell_area*rise.sum(axis=(1,2))
    power_in=POWERS.sum(axis=1)
    source_error=float(np.max(np.abs(B.sum(axis=0)-power_in)))
    balance=float(np.max(np.abs(energy_out-power_in)))
    max_residual=float(np.max(np.abs(plate.A@rise.reshape(2,-1).T-B)))
    reflected=INITIAL.copy();reflected[:,0]=25-reflected[:,0]
    rp,rg,_=plate.evaluate(reflected,grids=True)
    symmetry=float(np.max(np.abs(rg-grids[:,:,::-1])))
    doubled=plate.evaluate(INITIAL,POWERS*2)
    linearity=float(np.max(np.abs((doubled-TCOOL)-2*(peaks-TCOOL))))
    zero=plate.evaluate(INITIAL,np.zeros_like(POWERS))
    zero_error=float(np.max(abs(zero-TCOOL)))
    uniform_power=54.0
    uniform_source=np.full(plate.n*plate.n,uniform_power/(plate.n*plate.n))
    uniform_rise=plate.solve(uniform_source)
    uniform_analytic=uniform_power/(H*L*L)
    uniform_error=float(np.max(np.abs(uniform_rise-uniform_analytic)))
    tests={'source_power_conservation_max_abs_W':source_error,
      'vertical_energy_balance_max_abs_W':balance,'linear_system_max_residual_W':max_residual,
      'minimum_temperature_rise_K':float(rise.min()),'reflection_symmetry_max_abs_K':symmetry,
      'doubling_power_linearity_peak_error_K':linearity,'zero_power_peak_error_K':zero_error,
      'uniform_source_analytic_solution_error_K':uniform_error,
      'checks_pass':bool(source_error<1e-9 and balance<1e-8 and max_residual<1e-9 and rise.min()>=0 and symmetry<1e-8 and linearity<1e-8 and zero_error<1e-8 and uniform_error<1e-8)}
    invalid={
        'nan':np.full((4,2),np.nan),
        'positive_infinity':np.full((4,2),np.inf),
        'negative_infinity':np.full((4,2),-np.inf),
        'flat_shape':INITIAL.ravel(),
        'three_chiplets':INITIAL[:3],
        'extra_coordinate':np.ones((4,3)),
        'nonnumeric':[['bad','data']]*4,
        'overlap':np.repeat([[10.,10.]],4,axis=0),
        'outside_plate':INITIAL+25,
    }
    negative_results={name:bool(not legal(value)) for name,value in invalid.items()}
    api_rejects={}
    for name,value in invalid.items():
        try:plate.evaluate(value)
        except ValueError:api_rejects[name]=True
        else:api_rejects[name]=False
    tests['geometry_negative_checks_rejected']=negative_results
    tests['solver_api_negative_checks_rejected']=api_rejects
    tests['checks_pass']=bool(tests['checks_pass'] and all(negative_results.values()) and all(api_rejects.values()))
    if not tests['checks_pass']:raise AssertionError(tests)
    return tests,{'positions_mm':INITIAL.tolist(),'workload_peak_C':peaks.tolist(),'grids_C':grids.tolist()}


def main():
    tests,initial=validate_model();runs=[];surrogate_metrics=[]
    heldout_rng=np.random.default_rng(90001)
    heldout=[sample(heldout_rng) for _ in range(TEST)]
    refplate=Plate(BASE_N)
    true=np.array([refplate.evaluate(x) for x in heldout])
    for seed in SEEDS:
        t=time.perf_counter();rng=np.random.default_rng(seed)
        layouts=[INITIAL.copy()]+[sample(rng) for _ in range(TRAIN-1)]
        plate=Plate(BASE_N);values=np.array([plate.evaluate(x) for x in layouts])
        common_wall=time.perf_counter()-t
        t=time.perf_counter();model=fit_surrogate(layouts,values,seed);train_wall=time.perf_counter()-t
        pred=model.predict(np.array([features(x) for x in heldout]))
        errors=pred-true;actualscore=true.max(axis=1);predscore=pred.max(axis=1)
        actualtop=set(np.argsort(actualscore)[:10]);predtop=set(np.argsort(predscore)[:10])
        sm={'seed':seed,'train_examples':TRAIN,'untouched_test_examples':TEST,
            'mae_all_workloads_C':float(mean_absolute_error(true,pred)),
            'rmse_all_workloads_C':float(np.sqrt(mean_squared_error(true,pred))),
            'p95_abs_error_C':float(np.quantile(abs(errors),.95)),
            'max_abs_error_C':float(abs(errors).max()),
            'objective_spearman_rho':float(spearmanr(actualscore,predscore).statistic),
            'top10_overlap_fraction':len(actualtop&predtop)/10,
            'train_wall_seconds':train_wall,'common_initial_design_wall_seconds':common_wall,
            'per_workload_mae_C':np.mean(abs(errors),axis=0).tolist(),
            'heldout_true_peak_C':true.tolist(),'heldout_predicted_peak_C':pred.tolist()}
        surrogate_metrics.append(sm)
        for method in ['random','local_annealing','surrogate_screened']:
            result=optimize(seed,method,layouts,values,model)
            result['end_to_end_wall_seconds']=common_wall+result['additional_stage_wall_seconds']+(train_wall if method=='surrogate_screened' else 0)
            result['search_stage_wall_seconds']=result['end_to_end_wall_seconds']
            runs.append(result)
            print(seed,method,round(result['best_objective_C'],3),'C',round(result['end_to_end_wall_seconds'],3),'s',flush=True)
    # Finer mesh results are final evaluation only; never used by optimization.
    fine=Plate(80);unseen=Plate(80)
    for run in runs:
        xy=np.array(run['best_positions_mm'])
        f=fine.evaluate(xy);u=unseen.evaluate(xy,UNSEEN_POWER)
        run['final_80x80_workload_peak_C']=f.tolist()
        run['final_80x80_objective_C']=float(max(f))
        run['final_unused_balanced_workload_peak_C']=float(u[0])
        run['mesh40_to80_objective_delta_K']=float(max(f)-run['best_objective_C'])
    winner=min(runs,key=lambda x:x['best_objective_C'])
    xy=np.array(winner['best_positions_mm'])
    refinement=[]
    for n in [20,40,80,120]:
        p=Plate(n);v=p.evaluate(xy);refinement.append({'n':n,'dx_mm':25/n,'workload_peak_C':v.tolist(),'max_C':float(max(v))})
    summary={}
    for method in ['random','local_annealing','surrogate_screened']:
        rs=[r for r in runs if r['method']==method]
        summary[method]={'mean_best_objective_C':float(np.mean([r['best_objective_C'] for r in rs])),
          'std_best_objective_C':float(np.std([r['best_objective_C'] for r in rs],ddof=1)),
          'min_best_objective_C':min(r['best_objective_C'] for r in rs),
          'max_best_objective_C':max(r['best_objective_C'] for r in rs),
          'mean_end_to_end_seconds':float(np.mean([r['end_to_end_wall_seconds'] for r in rs])),
          'mean_search_stage_seconds':float(np.mean([r['search_stage_wall_seconds'] for r in rs])),
          'mean_final_80x80_objective_C':float(np.mean([r['final_80x80_objective_C'] for r in rs]))}
    # Render-only replay surfaces are evaluated after search and never feed it.
    # Store 10x10 cell-area means for display; all objective values above remain
    # unsmoothed full-resolution 40x40 simulator maxima.
    replay_begin=time.perf_counter(); replay_plate=Plate(BASE_N); replay_cache={}
    for run in runs:
        for item in run['history']:
            key=tuple(np.array(item['positions_mm']).ravel())
            if key not in replay_cache:
                _,g,_=replay_plate.evaluate(np.array(item['positions_mm']),grids=True)
                replay_cache[key]=np.round(g.reshape(2,10,4,10,4).mean(axis=(2,4)),3).tolist()
            item['display_grids_C']=replay_cache[key]
    replay_seconds=time.perf_counter()-replay_begin
    openblas=next((pool for pool in threadpool_info()
        if pool.get('user_api')=='blas' and pool.get('internal_api')=='openblas'),{})
    results={'label':'SYNTHETIC EDUCATIONAL FINITE-VOLUME EXPERIMENT; NOT GPU/CHIP SIGNOFF; NO JEV/LLM CALLS',
      'equation':'-k*t*laplacian(T)+h*(T-Tcool)=q_double_prime',
      'parameters':{'plate_size_mm':[25,25],'effective_conductivity_W_per_m_K':K,'plate_thickness_mm':THICK*1000,
        'vertical_conductance_W_per_m2_K':H,'coolant_C':TCOOL,'lateral_boundaries':'adiabatic; no in-plane heat loss at four edges',
        'source':'uniform flux in fixed chiplet rectangles; exact rectangle/cell overlap integration',
        'chiplet_sizes_mm':SIZES.tolist(),'workloads_W':POWERS.tolist(),'unused_final_workload_W':UNSEEN_POWER.tolist(),
        'minimum_nonoverlap_gap_mm':GAP,'placement_grid_mm':.5,'thermal_grid':[BASE_N,BASE_N]},
      'protocol':{'search_evaluations_per_method_per_seed':TRAIN+ADDITIONAL,'common_initial_examples':TRAIN,
         'adaptive_or_random_additional_examples':ADDITIONAL,'seeds':SEEDS,
         'heldout_test_examples':TEST,'heldout_test_seed':90001,
         'surrogate':'ExtraTreesRegressor; 120 estimators; min_samples_leaf=2; geometry/pair-distance features',
         'surrogate_refit_interval':12,'proposal_pool_per_step':128,
         'screened_candidates_note':'Counts candidate scoring instances; duplicates within a proposal batch can occur. Not a count of globally unique layouts.',
         'surrogate_uncertainty':'No predictive uncertainty or risk-bound calibration is implemented.',
         'objective':'minimize worst plate-cell temperature across two workloads',
         'fairness':'Each method charged all 120 initial simulator samples plus 72 additions; common pool per seed. Random and local do not pay surrogate fit overhead. No claim versus frontier models.',
         'not_RL':'Surrogate-assisted search and annealing; no policy-gradient or learned routing policy.'},
      'validation':tests,'initial':initial,'surrogate_metrics':surrogate_metrics,'runs':runs,
      'summary':summary,'winner':{'seed':winner['seed'],'method':winner['method'],'positions_mm':winner['best_positions_mm'],
         'objective_C':winner['best_objective_C'],'workload_peak_C':winner['best_workload_peak_C'],
         'grids_C':winner['best_grids_C']},'winner_mesh_refinement':refinement,
      'costs':{'external_API_calls':0,'external_API_dollars':0,'wall_seconds_total':time.perf_counter()-START,
         'local_compute_dollars':'not metered; not zero cost',
         'render_only_replay_calls':replay_plate.calls,
         'render_only_replay_seconds':replay_seconds,
         'simulator_search_calls_if_methods_charged_independently':len(SEEDS)*3*(TRAIN+ADDITIONAL),
         'reused_common_search_simulator_calls_saved':len(SEEDS)*2*TRAIN,
         'test_set_calls':TEST,'final_evaluation_calls_excluded_from_search_budget':'1 final verification per run; 80x80 evaluation of each finalist plus held-out workload; four winner refinement meshes'},
      'versions':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__,'sklearn':sklearn.__version__,
          'openblas_coretype':os.environ.get('OPENBLAS_CORETYPE','auto'),
          'openblas_architecture':openblas.get('architecture'),'openblas_version':openblas.get('version'),
          'threadpoolctl':threadpoolctl_version},
      'display_grid_note':'Each history display_grids_C is a 10x10 area-average of the actual 40x40 solver grid, rounded to 0.001 C. Objective and workload_peak_C are full-resolution maxima, not display-grid maxima.',
      'timing_scope':{'preferred_run_field':'search_stage_wall_seconds','preferred_summary_field':'mean_search_stage_seconds',
          'legacy_aliases':['end_to_end_wall_seconds','mean_end_to_end_seconds'],
          'includes':'Common initial sampling and simulation including its one Plate construction/factorization; additional search; final 40x40 winner verification; initial surrogate fitting and refitting where used.',
          'excludes':'Per-arm Plate construction/factorization; held-out accuracy evaluation; 80x80 final audit and unused workload; 20/40/80/120 mesh refinement; replay-grid generation; plot rendering; overall environment setup.',
          'warning':'Legacy end_to_end names do not mean full application or production latency.'},
      'geometry_gap_note':'Conservative axis-aligned separation: at least one coordinate axis separates each footprint pair by 0.5 mm. This is stricter than a general Euclidean corner-clearance constraint.',
      'limits':['Synthetic powers, geometry, cooling and material assumptions; no real chip measurements.',
        'Reports spreader plate temperature; not die junction temperature.',
        'No chiplet timing, power delivery, interconnect length/bandwidth, reliability or manufacturability signoff.',
        'Surrogate held-out data are drawn from the same synthetic sampling distribution; adaptive search can exploit errors.',
        'Simulator winners are rechecked; the surrogate does not approve layouts alone.',
        'Three seeds demonstrate feasibility; no broad statistical superiority claim.',
        'No Jev latency/cost/calibration or actual agent token-use measurement.',
        'Nominal parameters are deterministic; physical parameter uncertainty is not modeled.']}
    (OUT/'results.json').write_text(json.dumps(results,indent=2))
    make_plots(results)
    print(json.dumps({'summary':summary,'surrogate_metrics':[{k:v for k,v in s.items() if not k.startswith('heldout_')} for s in surrogate_metrics],
        'validation':tests,'refinement':refinement,'wall_seconds':time.perf_counter()-START},indent=2),flush=True)

def draw_layout(ax,xy,grid,title,vmin,vmax):
    im=ax.imshow(grid,origin='lower',extent=[0,25,0,25],cmap='inferno',vmin=vmin,vmax=vmax)
    for i,((cx,cy),(sx,sy)) in enumerate(zip(xy,SIZES)):
        ax.add_patch(plt.Rectangle((cx-sx/2,cy-sy/2),sx,sy,fill=False,edgecolor='cyan',linewidth=1.7))
        ax.text(cx,cy,str(i+1),ha='center',va='center',color='white',weight='bold')
    ax.set_title(title);ax.set_xlabel('x (mm)');ax.set_ylabel('y (mm)');return im

def make_plots(r):
    plt.rcParams.update({'font.size':10,'figure.facecolor':'white'})
    initial=np.array(r['initial']['grids_C']);best=np.array(r['winner']['grids_C'])
    lo=min(initial.min(),best.min());hi=max(initial.max(),best.max())
    fig,axs=plt.subplots(2,2,figsize=(11,9),layout='constrained')
    for w in range(2):
        draw_layout(axs[w,0],np.array(r['initial']['positions_mm']),initial[w],f'Initial, workload {w+1}: {initial[w].max():.2f} °C',lo,hi)
        im=draw_layout(axs[w,1],np.array(r['winner']['positions_mm']),best[w],f'Best verified, workload {w+1}: {best[w].max():.2f} °C',lo,hi)
    fig.colorbar(im,ax=axs,label='Synthetic spreader temperature (°C)',shrink=.8)
    fig.suptitle('Synthetic coupled chiplet placement • finite-volume plate model\nIllustration only; not GPU or physical-design signoff',fontsize=14)
    fig.savefig(OUT/'thermal_layouts.png',dpi=160);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    colors={'random':'#667085','local_annealing':'#2b8a3e','surrogate_screened':'#7c3aed'}
    for method in colors:
        histories=np.array([[h['best_so_far_C'] for h in run['history']] for run in r['runs'] if run['method']==method])
        xs=np.arange(1,histories.shape[1]+1)
        axs[0].plot(xs,histories.mean(axis=0),label=method.replace('_',' '),color=colors[method])
        axs[0].fill_between(xs,histories.min(axis=0),histories.max(axis=0),alpha=.12,color=colors[method])
    axs[0].axvline(TRAIN,color='black',linestyle='--',lw=1,label='shared initial data end')
    axs[0].set(xlabel='Thermal simulator evaluations charged per method',ylabel='Best worst-workload temperature (°C)',title='Equal simulator budget; 3 seeds, range shaded');axs[0].legend(fontsize=8)
    sm=r['surrogate_metrics'][0]
    x=np.max(sm['heldout_true_peak_C'],axis=1);y=np.max(sm['heldout_predicted_peak_C'],axis=1)
    axs[1].scatter(x,y,s=23,alpha=.7,color='#7c3aed')
    lim=[min(x.min(),y.min()),max(x.max(),y.max())];axs[1].plot(lim,lim,'k--',lw=1)
    axs[1].set(xlabel='Simulator worst-workload temperature (°C)',ylabel='Surrogate prediction (°C)',title=f'Untouched held-out set; seed {sm["seed"]}\nSpearman ρ={sm["objective_spearman_rho"]:.2f}; MAE={sm["mae_all_workloads_C"]:.2f} °C')
    fig.suptitle('Synthetic benchmark: search gains and surrogate limitations',fontsize=14)
    fig.savefig(OUT/'optimization_comparison.png',dpi=160);plt.close(fig)

if __name__=='__main__':main()
