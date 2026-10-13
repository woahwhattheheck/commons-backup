from __future__ import annotations

import argparse, json, math, sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import rasterio
from rasterio.windows import Window
from scipy.ndimage import distance_transform_edt, gaussian_filter, gaussian_laplace, sobel
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

CRS = "EPSG:32611"
RES_M = 100.0
SUPPORT_M = 300.0
ALPHA, BETA = 0.2, 0.8
MODEL_VERSION = 1


class GemsError(ValueError):
    pass


def _prob(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    if a.ndim != 2 or not np.isfinite(a).all() or np.any((a < 0) | (a > 1)):
        raise GemsError("prediction must be finite 2-D probabilities in [0,1]")
    return a


def _truth(a: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    a = np.asarray(a)
    if a.ndim != 2 or a.shape != shape or not np.all(np.isin(np.unique(a), [0, 1, False, True])):
        raise GemsError("truth must be a binary 2-D raster matching prediction")
    return a.astype(bool)


def _max_weighted_neighbor(p: np.ndarray, radius: float) -> np.ndarray:
    out = np.zeros_like(p, dtype=np.float64)
    lim = int(math.ceil(radius))
    h, w = p.shape
    for dy in range(-lim, lim + 1):
        for dx in range(-lim, lim + 1):
            d = math.hypot(dy, dx)
            weight = max(1.0 - d / radius, 0.0)
            if weight <= 0:
                continue
            y0, y1 = max(0, -dy), min(h, h - dy)
            x0, x1 = max(0, -dx), min(w, w - dx)
            if y0 >= y1 or x0 >= x1:
                continue
            np.maximum(out[y0:y1, x0:x1], p[y0+dy:y1+dy, x0+dx:x1+dx] * weight,
                       out=out[y0:y1, x0:x1])
    return out


def distance_weighted_tversky(pred: np.ndarray, truth: np.ndarray, *, radius_px: float = 3.0,
                               alpha: float = ALPHA, beta: float = BETA) -> dict[str, float]:
    p, r = _prob(pred), float(radius_px)
    g = _truth(truth, p.shape)
    if r <= 0 or alpha < 0 or beta < 0:
        raise GemsError("metric radius must be positive and alpha/beta non-negative")
    if g.any():
        strongest = _max_weighted_neighbor(p, r)
        tp = float(strongest[g].sum())
        fn = float(g.sum() - tp)
        proximity = np.maximum(1.0 - distance_transform_edt(~g) / r, 0.0)
        fp = float((p * (1.0 - proximity)).sum())
    else:
        tp, fn, fp = 0.0, 0.0, float(p.sum())
    denom = tp + alpha * fp + beta * fn
    return {"score": float(tp / denom) if denom else 1.0, "tp_w": tp, "fp_w": fp, "fn_w": fn}


def distance_weighted_tversky_masked(
    pred: np.ndarray,
    truth: np.ndarray,
    *,
    exclude_mask: np.ndarray | None = None,
    valid_mask: np.ndarray | None = None,
    radius_px: float = 3.0,
    alpha: float = ALPHA,
    beta: float = BETA,
) -> dict[str, float | int]:
    """Score only the admitted evaluation domain.

    The GEMS organizers clarified that the provided known-fault training raster is
    a pixel-exact exclusion mask: only those pixels are removed from evaluation;
    neighboring pixels remain fully scored and can contain correction faults.
    valid_mask separately excludes nodata/null regions from the local raster domain.
    """
    p_raw = np.asarray(pred, dtype=np.float64)
    if p_raw.ndim != 2:
        raise GemsError("prediction must be a 2-D raster")
    g = _truth(truth, p_raw.shape)
    domain = np.ones(p_raw.shape, dtype=bool)

    if valid_mask is not None:
        valid = np.asarray(valid_mask)
        if valid.ndim != 2 or valid.shape != p_raw.shape:
            raise GemsError("valid mask must be a 2-D raster matching prediction")
        domain &= valid.astype(bool)

    valid_before_known = domain.copy()
    known = np.zeros(p_raw.shape, dtype=bool)
    if exclude_mask is not None:
        known = _truth(exclude_mask, p_raw.shape)
        domain &= ~known

    if not domain.any():
        raise GemsError("metric evaluation domain contains no pixels")

    active = p_raw[domain]
    if not np.isfinite(active).all() or np.any((active < 0) | (active > 1)):
        raise GemsError("prediction must be finite probabilities in [0,1] on evaluated pixels")

    # A masked pixel contributes neither prediction mass nor ground truth. Do not
    # dilate the known-fault mask: the published 300 m kernel applies only to
    # distance from new-fault truth, and correction faults can sit beside known
    # traces.
    p = np.zeros_like(p_raw, dtype=np.float64)
    p[domain] = active
    g = g & domain
    result = distance_weighted_tversky(
        p,
        g,
        radius_px=radius_px,
        alpha=alpha,
        beta=beta,
    )
    result["evaluated_pixels"] = int(domain.sum())
    result["excluded_pixels"] = int((~domain).sum())
    result["excluded_known_fault_pixels"] = int((known & valid_before_known).sum())
    return result


def robust_stats(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    arr = np.asarray(arr, dtype=np.float32)
    if arr.ndim != 3:
        raise GemsError("features must be (bands,height,width)")
    med, scale = [], []
    for b in arr:
        x = b[np.isfinite(b)]
        if x.size < 4:
            raise GemsError("every band needs >=4 finite values")
        q25, q50, q75 = np.quantile(x, [0.25, 0.5, 0.75])
        s = float(q75 - q25)
        if s < 1e-6:
            s = max(float(np.std(x)), 1.0)
        med.append(float(q50)); scale.append(s)
    return np.asarray(med, np.float32), np.asarray(scale, np.float32)


def _line_response(x: np.ndarray) -> np.ndarray:
    best = np.zeros_like(x, dtype=np.float32)
    for sigma in (1.0, 2.0):
        hxx = gaussian_filter(x, sigma, order=(0, 2), mode="nearest")
        hyy = gaussian_filter(x, sigma, order=(2, 0), mode="nearest")
        hxy = gaussian_filter(x, sigma, order=(1, 1), mode="nearest")
        tr = hxx + hyy
        disc = np.sqrt(np.maximum((hxx-hyy)**2 + 4*hxy**2, 0))
        a, b = np.abs((tr-disc)/2), np.abs((tr+disc)/2)
        small, large = np.minimum(a,b), np.maximum(a,b)
        response = ((large-small)/(large+small+1e-6) * np.tanh(large*sigma*sigma)).astype(np.float32)
        np.maximum(best, response, out=best)
    return best


def feature_stack(arr: np.ndarray, med: np.ndarray, scale: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, np.float32)
    if arr.ndim != 3 or med.shape != (arr.shape[0],) or scale.shape != (arr.shape[0],):
        raise GemsError("normalization stats do not match feature bands")
    x = np.where(np.isfinite(arr), arr, med[:,None,None])
    x = np.clip((x-med[:,None,None])/scale[:,None,None], -8, 8)
    parts, grads, lines = [], [], []
    for b in x:
        gx, gy = sobel(b, axis=1, mode="nearest")/8, sobel(b, axis=0, mode="nearest")/8
        grad = np.hypot(gx, gy).astype(np.float32)
        line = _line_response(b)
        parts += [b.astype(np.float32), grad, np.abs(gaussian_laplace(b, 1.2)).astype(np.float32), line]
        grads.append(grad); lines.append(line)
    gc, lc = np.stack(grads), np.stack(lines)
    parts += [gc.max(0), gc.mean(0), lc.max(0), lc.mean(0)]
    return np.stack(parts).astype(np.float32)


def block_folds(rows: np.ndarray, cols: np.ndarray, *, block: int = 128, splits: int = 5) -> np.ndarray:
    if block <= 0 or splits < 2:
        raise GemsError("invalid spatial split")
    return (((np.asarray(rows)//block)*73856093) ^ ((np.asarray(cols)//block)*19349663)) % splits


def choose_samples(labels: np.ndarray, *, max_positive: int = 50000, negatives_per_positive: float = 4,
                   seed: int = 20260913) -> tuple[np.ndarray,np.ndarray,np.ndarray]:
    y = _truth(labels, labels.shape)
    rng = np.random.default_rng(seed)
    pos = np.argwhere(y)
    if not len(pos):
        raise GemsError("training labels contain no positive fault pixels")
    if len(pos) > max_positive:
        pos = pos[rng.choice(len(pos), max_positive, replace=False)]
    d = distance_transform_edt(~y)
    neg = np.argwhere(~y)
    want = max(1, int(round(len(pos)*negatives_per_positive)))
    hard = neg[d[neg[:,0],neg[:,1]] <= 6]
    far = neg[d[neg[:,0],neg[:,1]] > 6]
    chosen = []
    for pool, n in ((hard, want//2), (far, want-want//2)):
        if len(pool):
            chosen.append(pool[rng.choice(len(pool), min(n,len(pool)), replace=False)])
    negsel = np.concatenate(chosen) if chosen else np.empty((0,2), int)
    coords = np.concatenate([pos, negsel])
    target = np.concatenate([np.ones(len(pos),np.uint8), np.zeros(len(negsel),np.uint8)])
    order = rng.permutation(len(coords))
    return coords[order,0], coords[order,1], target[order]


def fit_model(X: np.ndarray, y: np.ndarray, rows: np.ndarray, cols: np.ndarray, *, block_size: int = 128, n_splits: int = 5, holdout_fold: int | None = None, random_state: int = 20260913, seed: int | None = None) -> dict[str,Any]:
    X, y = np.asarray(X,np.float32), np.asarray(y,np.uint8)
    if seed is not None:
        random_state = seed
    folds = block_folds(rows, cols, block=block_size, splits=n_splits)
    hold = int(np.bincount(folds, minlength=n_splits).argmax()) if holdout_fold is None else int(holdout_fold)
    if hold < 0 or hold >= n_splits:
        raise GemsError("holdout_fold outside split range")
    train, valid = folds != hold, folds == hold
    if train.sum() < 20 or len(np.unique(y[train])) < 2:
        train[:] = True; valid[:] = False
    clf = HistGradientBoostingClassifier(max_iter=220, learning_rate=.07, max_leaf_nodes=31,
                                         l2_regularization=.5, random_state=random_state).fit(X[train],y[train])
    calibrator = None; brier = None
    if valid.any() and len(np.unique(y[valid])) == 2:
        raw = clf.predict_proba(X[valid])[:,1]
        calibrator = LogisticRegression(C=1, solver="lbfgs", random_state=random_state).fit(raw[:,None],y[valid])
        p = calibrator.predict_proba(raw[:,None])[:,1]
        brier = float(np.mean((p-y[valid])**2))
    return {"model_version":MODEL_VERSION,"classifier":clf,"calibrator":calibrator,
            "training":{"samples":int(len(y)),"positives":int(y.sum()),"holdout_fold":hold,"holdout_brier":brier}}


def _predict(bundle: dict[str,Any], X: np.ndarray) -> np.ndarray:
    p = bundle["classifier"].predict_proba(np.asarray(X,np.float32))[:,1]
    c = bundle.get("calibrator")
    return c.predict_proba(p[:,None])[:,1] if c is not None else p


def validate_feature(src: rasterio.io.DatasetReader) -> None:
    if src.crs is None or src.crs.to_string() != CRS:
        raise GemsError(f"feature CRS must be {CRS}")
    if abs(abs(float(src.res[0]))-RES_M) > 1e-6 or abs(abs(float(src.res[1]))-RES_M) > 1e-6:
        raise GemsError("feature resolution must be 100m")
    if src.count < 1:
        raise GemsError("feature raster must have at least one band")


def validate_alignment(feature_path: str|Path, label_path: str|Path) -> None:
    with rasterio.open(feature_path) as f, rasterio.open(label_path) as y:
        validate_feature(f)
        if y.count != 1 or f.shape != y.shape or f.crs != y.crs or not f.transform.almost_equals(y.transform):
            raise GemsError("label raster must be one band on exact feature grid")


def _stats_from_raster(path: str|Path) -> tuple[np.ndarray,np.ndarray]:
    with rasterio.open(path) as src:
        validate_feature(src)
        stride = max(1, int(max(src.height,src.width)/512))
        arr = src.read(window=Window(0,0,src.width,src.height), out_shape=(src.count,max(1,src.height//stride),max(1,src.width//stride)), masked=True).filled(np.nan)
    return robust_stats(arr)


def train_from_rasters(feature_path: str|Path, label_path: str|Path, model_path: str|Path, *, max_positive: int=50000,
                       negatives_per_positive: float=4, seed: int=20260913) -> dict[str,Any]:
    validate_alignment(feature_path,label_path)
    med, scale = _stats_from_raster(feature_path)
    with rasterio.open(label_path) as src:
        labels = src.read(1)
    rows, cols, y = choose_samples(labels,max_positive=max_positive,negatives_per_positive=negatives_per_positive,seed=seed)
    with rasterio.open(feature_path) as src:
        raw = src.read(masked=True).filled(np.nan).astype(np.float32)
        valid = np.all(np.isfinite(raw[:,rows,cols]),axis=0)
        stack = feature_stack(raw,med,scale)
        X = stack[:,rows[valid],cols[valid]].T
        rows,cols,y = rows[valid],cols[valid],y[valid]
        bundle = fit_model(X,y,rows,cols,random_state=seed)
        bundle.update({"band_count":src.count,"medians":med,"scales":scale,"shape":[src.height,src.width],"transform":tuple(src.transform)})
    Path(model_path).parent.mkdir(parents=True,exist_ok=True); joblib.dump(bundle,model_path,compress=3)
    return bundle


def predict_raster(feature_path: str|Path, model_path: str|Path, output_path: str|Path, *, tile_size: int=256, halo: int=6) -> None:
    bundle = joblib.load(model_path)
    if bundle.get("model_version") != MODEL_VERSION:
        raise GemsError("unsupported model version")
    with rasterio.open(feature_path) as src:
        validate_feature(src)
        if src.count != bundle["band_count"] or [src.height,src.width] != bundle["shape"] or tuple(src.transform) != tuple(bundle["transform"]):
            raise GemsError("feature raster differs from training source contract")
        profile = src.profile.copy(); profile.update(driver="GTiff",count=1,dtype="float32",nodata=np.nan,compress="deflate",predictor=3)
        Path(output_path).parent.mkdir(parents=True,exist_ok=True)
        with rasterio.open(output_path,"w",**profile) as dst:
            for r0 in range(0,src.height,tile_size):
                for c0 in range(0,src.width,tile_size):
                    h,w = min(tile_size,src.height-r0),min(tile_size,src.width-c0)
                    win = Window(c0-halo,r0-halo,w+2*halo,h+2*halo)
                    masked = src.read(window=win,boundless=True,masked=True,fill_value=np.nan)
                    raw = masked.filled(np.nan).astype(np.float32)
                    valid = ~np.any(np.ma.getmaskarray(masked),axis=0)
                    stack = feature_stack(raw,np.asarray(bundle["medians"]),np.asarray(bundle["scales"]))
                    core = stack[:,halo:halo+h,halo:halo+w]
                    p = _predict(bundle,np.moveaxis(core,0,-1).reshape(-1,core.shape[0])).reshape(h,w)
                    p = np.where(valid[halo:halo+h,halo:halo+w],p,np.nan).astype(np.float32)
                    dst.write(p,1,window=Window(c0,r0,w,h))


def validate_submission(feature_path: str|Path, submission_path: str|Path) -> dict[str,Any]:
    with rasterio.open(feature_path) as f, rasterio.open(submission_path) as s:
        validate_feature(f)
        if s.count != 1 or s.dtypes[0] != "float32" or f.shape != s.shape or f.crs != s.crs or not f.transform.almost_equals(s.transform):
            raise GemsError("submission must be one float32 band on exact feature grid")
        a = s.read(1); finite = np.isfinite(a)
        if finite.any() and np.any((a[finite] < 0) | (a[finite] > 1)):
            raise GemsError("submission probabilities must be in [0,1]")
        return {"width":s.width,"height":s.height,"crs":s.crs.to_string(),"dtype":s.dtypes[0],
                "finite_pixels":int(finite.sum()),"null_pixels":int((~finite).sum()),
                "min_probability":float(a[finite].min()) if finite.any() else None,
                "max_probability":float(a[finite].max()) if finite.any() else None}


def score_rasters(
    pred_path: str | Path,
    label_path: str | Path,
    known_fault_mask_path: str | Path | None = None,
) -> dict[str, float | int]:
    with rasterio.open(pred_path) as p, rasterio.open(label_path) as y:
        if p.count != 1 or y.count != 1 or p.shape != y.shape or p.crs != y.crs or not p.transform.almost_equals(y.transform):
            raise GemsError("prediction and labels must share one exact grid")
        if abs(abs(float(p.res[0]))-abs(float(p.res[1]))) > 1e-6:
            raise GemsError("metric expects square pixels")

        pred = p.read(1, masked=True)
        truth = y.read(1, masked=True)
        valid = ~np.ma.getmaskarray(pred) & ~np.ma.getmaskarray(truth)
        pred_arr = np.asarray(pred.filled(np.nan), dtype=np.float64)
        truth_arr = np.asarray(truth.filled(0))
        shape, crs, transform = p.shape, p.crs, p.transform
        radius_px = SUPPORT_M / abs(float(p.res[0]))

    known = None
    if known_fault_mask_path is not None:
        with rasterio.open(known_fault_mask_path) as k:
            if k.count != 1 or k.shape != shape or k.crs != crs or not k.transform.almost_equals(transform):
                raise GemsError("known-fault mask must be one band on exact prediction grid")
            known_ma = k.read(1, masked=True)
            valid &= ~np.ma.getmaskarray(known_ma)
            known = np.asarray(known_ma.filled(0))

    return distance_weighted_tversky_masked(
        pred_arr,
        truth_arr,
        exclude_mask=known,
        valid_mask=valid,
        radius_px=radius_px,
    )



# Public compatibility names used by the test harness and notebooks.
robust_band_stats = robust_stats

def blocked_fold_ids(rows: np.ndarray, cols: np.ndarray, *, block_size: int = 128, n_splits: int = 5) -> np.ndarray:
    return block_folds(rows, cols, block=block_size, splits=n_splits)

def choose_training_coordinates(labels: np.ndarray, *, max_positive: int = 50000, negatives_per_positive: float = 4, seed: int = 20260913):
    return choose_samples(labels, max_positive=max_positive, negatives_per_positive=negatives_per_positive, seed=seed)

def predict_matrix(bundle: dict[str, Any], matrix: np.ndarray) -> np.ndarray:
    return _predict(bundle, matrix)

def validate_feature_raster(src: rasterio.io.DatasetReader) -> None:
    return validate_feature(src)

def validate_label_alignment(feature_path: str|Path, label_path: str|Path) -> None:
    return validate_alignment(feature_path, label_path)

def _parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="DOE GEMS fault-probability solver"); s=p.add_subparsers(dest="cmd",required=True)
    q=s.add_parser("train"); q.add_argument("--features",required=True); q.add_argument("--labels",required=True); q.add_argument("--model",required=True); q.add_argument("--max-positive",type=int,default=50000); q.add_argument("--negatives-per-positive",type=float,default=4); q.add_argument("--seed",type=int,default=20260913)
    q=s.add_parser("predict"); q.add_argument("--features",required=True); q.add_argument("--model",required=True); q.add_argument("--output",required=True); q.add_argument("--tile-size",type=int,default=256)
    q=s.add_parser("verify-submission"); q.add_argument("--features",required=True); q.add_argument("--submission",required=True)
    q=s.add_parser("metric"); q.add_argument("--prediction",required=True); q.add_argument("--labels",required=True); q.add_argument("--known-fault-mask")
    return p


def main(argv: list[str]|None=None) -> int:
    try:
        a=_parser().parse_args(argv)
        if a.cmd=="train": out=train_from_rasters(a.features,a.labels,a.model,max_positive=a.max_positive,negatives_per_positive=a.negatives_per_positive,seed=a.seed)["training"]
        elif a.cmd=="predict": predict_raster(a.features,a.model,a.output,tile_size=a.tile_size); out=validate_submission(a.features,a.output)
        elif a.cmd=="verify-submission": out=validate_submission(a.features,a.submission)
        else: out=score_rasters(a.prediction,a.labels,a.known_fault_mask)
        print(json.dumps(out,sort_keys=True,indent=2,default=float)); return 0
    except (GemsError,OSError,ValueError,rasterio.errors.RasterioError) as exc:
        print(f"GEMS solver error: {exc}",file=sys.stderr); return 2

if __name__=="__main__": raise SystemExit(main())
