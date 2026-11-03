"""
The three candidate models. Each is ONE Pipeline: the phase 2 preprocessor, then the model, so
preprocessing is always refitted on exactly the rows a model is trained on (also inside every
cross-validation fold while tuning).

No class weights: they would push every probability up, and the API returns a probability that should
mean what it says. Class imbalance is handled by the decision threshold instead (see evaluate.py).
"""
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.pipeline import Pipeline

from ml import features

SEED = 42
CV_FOLDS = 5
CANDIDATES = ("baseline", "logistic_regression", "gradient_boosting")

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
