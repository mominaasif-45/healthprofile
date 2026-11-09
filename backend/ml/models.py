"""
The three candidate models. Each is ONE Pipeline: the phase 2 preprocessor, then the model, so
preprocessing is always refitted on exactly the rows a model is trained on (also inside every
cross-validation fold while tuning).

No class weights: they would push every probability up, and the API returns a probability that should
mean what it says. Class imbalance is handled by the decision threshold instead (see evaluate.py).
"""
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV, StratifiedKFold
from sklearn.pipeline import Pipeline

from ml import features

SEED = 42
CV_FOLDS = 5
CANDIDATES = ("baseline", "logistic_regression", "gradient_boosting")  # Week 3 (noshow-1.0.0): do not change
# Week 4 workbench: Week 3's three plus a random forest. A comparison report only; it ships no new model.
WORKBENCH_CANDIDATES = ("baseline", "logistic_regression", "random_forest", "gradient_boosting")

# Small grids keep the experiment fast; tuning uses the training pile only (cross-validation).
PARAM_GRIDS = {
    "baseline": {},
    "logistic_regression": {"model__C": [0.01, 0.1, 1.0, 10.0]},
    "gradient_boosting": {
        "model__learning_rate": [0.05, 0.1],
        "model__max_depth": [2, 3],
        "model__max_iter": [100, 200],
    },
}


def _estimator(name):
    if name == "baseline":
        return DummyClassifier(strategy="prior")  # everyone gets the training no-show rate
    if name == "logistic_regression":
        return LogisticRegression(max_iter=2000)
    if name == "gradient_boosting":
        return HistGradientBoostingClassifier(early_stopping=False, random_state=SEED)
    if name == "random_forest":
        # n_jobs=1: one CPU core, so only one copy of the data in memory and identical results on every run.
        return RandomForestClassifier(random_state=SEED, n_jobs=1)
    raise ValueError(f"Unknown model: {name}")


def make_pipeline(name):
    return Pipeline([("preprocess", features.build_preprocessor()), ("model", _estimator(name))])


def fit_candidate(name, train):
    """
    Fit on the training pile. Returns (fitted pipeline, tuning info). Models with a grid are tuned by
    5-fold cross-validation on the training pile, scored by PR-AUC, then refitted on the whole pile.
    """
    X, y = features.features_of(train), features.target_of(train)
    grid = PARAM_GRIDS[name]
    if not grid:
        return make_pipeline(name).fit(X, y), {"best_params": {}, "cv_pr_auc": None}
    search = GridSearchCV(
        make_pipeline(name), grid, scoring="average_precision",
        cv=StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=SEED),
    )
    search.fit(X, y)
    params = {key.removeprefix("model__"): value for key, value in search.best_params_.items()}
    return search.best_estimator_, {"best_params": params, "cv_pr_auc": round(float(search.best_score_), 4)}


# ---------------------------------------------------------------- Week 4: random forest tuning
RF_SEARCH_TRIES = 10
# Depth and tree count are capped to keep memory and time low on a laptop.
RF_SEARCH_SPACE = {
    "model__n_estimators": [100, 200, 300],
    "model__max_depth": [4, 6, 8, 12],
    "model__min_samples_leaf": [5, 10, 20, 40],
    "model__max_features": ["sqrt", 0.5],
}


def cv_splitter():
    """The 5-fold stratified, shuffled, seeded split used for every Week 4 cross-validation."""
    return StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=SEED)


def tune_random_forest(train):
    """
    RandomizedSearchCV: 10 seeded settings, each scored by 5-fold cross-validated PR-AUC on the training pile
    only (preprocessing is refitted inside every fold), then the best one is refitted on the whole pile.
    Returns (fitted pipeline, tuning info, every try).
    """
    X, y = features.features_of(train), features.target_of(train)
    search = RandomizedSearchCV(
        make_pipeline("random_forest"), RF_SEARCH_SPACE, n_iter=RF_SEARCH_TRIES, scoring="average_precision",
        cv=cv_splitter(), random_state=SEED, n_jobs=1,
    )
    search.fit(X, y)
    cv = search.cv_results_
    tries = [
        {
            "params": {key.removeprefix("model__"): value for key, value in params.items()},
            "cv_pr_auc_mean": round(float(cv["mean_test_score"][i]), 4),
            "cv_pr_auc_sd": round(float(cv["std_test_score"][i]), 4),
        }
        for i, params in enumerate(cv["params"])
    ]
    best = tries[search.best_index_]
    return search.best_estimator_, {"best_params": best["params"], "cv_pr_auc": best["cv_pr_auc_mean"]}, tries
