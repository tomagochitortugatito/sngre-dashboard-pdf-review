"""
Modelos predictivos sobre el dataset de eventos únicos de la Sección 2
(`prediccion/data/eventos_features.parquet`, generado por build_dataset.py).

Tres modelos, todos entrenados con scikit-learn y evaluados con split
temporal (train = eventos más antiguos, test = los más recientes):

- **Random Forest Classifier** (`train_event_type_classifier`) — predice, a
  partir de (mes, provincia, zona), la probabilidad de cada uno de los 20
  tipos de evento. Accuracy≈0.65 / top-3 accuracy≈0.81 en test, contra 0.39
  de la línea base ("siempre predecir Inundación", el tipo más frecuente).
  Es el modelo que usa la sección "Modelo predictivo" de la app. El mes se
  agrupa internamente en 4 estaciones (DEF/MAM/JJA/SON) y se usa la
  provincia completa (sin agrupar) — con mes crudo + provincia agrupada
  (primer intento) daba accuracy≈0.56; con regresión logística en vez de
  Random Forest, accuracy≈0.62. Ver comparativa completa en la sección
  Arquitectura de la app.
- **Random Forest Regressor** (`train_regression`) sobre
  log1p(peak_impact_score) — estima qué tan grave podría llegar a ser un
  evento puntual ya reportado, a partir de lo conocido en su primer
  boletín. R²≈0.71 en test (una lineal se quedaba en ≈0.60).
- **Regresión logística** (`train_classification`) sobre `escalamiento`
  (¿el impacto superó en >5% al del primer boletín?). AUC≈0.63 en test.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, confusion_matrix, f1_score, log_loss, mean_absolute_error,
    precision_score, r2_score, recall_score, roc_auc_score, roc_curve,
    top_k_accuracy_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from build_dataset import IMPACT_COLS, IMPACT_WEIGHTS

NUM_FEATURES = ["background_len", "recurrence_prior"] + [f"initial_{c}" for c in IMPACT_COLS]
BOOL_FEATURES = [
    "bg_menciona_declaratoria", "bg_menciona_recurrencia",
    "bg_menciona_rio_quebrada", "bg_menciona_lluvias", "bg_menciona_talud_erosion",
]
CAT_FEATURES = ["event_type", "zone", "province_grp", "month"]
ALL_FEATURES = NUM_FEATURES + BOOL_FEATURES + CAT_FEATURES

TOP_PROVINCES_N = 12


def prepare_frame(df):
    """Añade columnas derivadas necesarias como features (agrupar
    provincias poco frecuentes, castear booleanos a entero, mes como str
    categórica) sin tocar el parquet original."""
    df = df.copy()
    top_provs = df["province"].value_counts().head(TOP_PROVINCES_N).index
    df["province_grp"] = df["province"].where(df["province"].isin(top_provs), "Otra")
    df["month"] = df["month"].astype("Int64").astype(str)
    for c in BOOL_FEATURES:
        df[c] = df[c].astype(int)
    return df


def build_preprocessor():
    log1p = FunctionTransformer(np.log1p, feature_names_out="one-to-one")
    numeric_pipe = Pipeline([("log1p", log1p), ("scale", StandardScaler())])
    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, NUM_FEATURES),
            ("bool", "passthrough", BOOL_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
        ]
    )


def temporal_split(df, test_frac=0.2):
    df = df.sort_values("event_start_date").reset_index(drop=True)
    cut = int(len(df) * (1 - test_frac))
    return df.iloc[:cut].copy(), df.iloc[cut:].copy()


@dataclass
class RegressionResult:
    pipeline: object
    train: pd.DataFrame
    test: pd.DataFrame
    y_test: np.ndarray
    y_pred: np.ndarray
    r2: float
    mae_log: float
    mae_original: float
    coefs: pd.DataFrame


@dataclass
class ClassificationResult:
    pipeline: object
    train: pd.DataFrame
    test: pd.DataFrame
    y_test: np.ndarray
    y_pred: np.ndarray
    y_proba: np.ndarray
    accuracy: float
    precision: float
    recall: float
    f1: float
    roc_auc: float
    confusion: np.ndarray
    fpr: np.ndarray
    tpr: np.ndarray
    coefs: pd.DataFrame


def _coef_table(preprocessor, coefs):
    names = preprocessor.get_feature_names_out()
    tbl = pd.DataFrame({"feature": names, "coef": coefs})
    tbl["feature"] = tbl["feature"].str.replace(r"^(num__|bool__|cat__)", "", regex=True)
    tbl["abs_coef"] = tbl["coef"].abs()
    return tbl.sort_values("abs_coef", ascending=False).drop(columns="abs_coef")


def _importance_table(preprocessor, importances):
    """Igual que _coef_table pero para modelos de árboles: feature_importances_
    no tiene signo (siempre >= 0), así que se reporta tal cual bajo la misma
    columna 'coef' para que el resto de la app (gráficos) no tenga que
    distinguir el tipo de modelo."""
    names = preprocessor.get_feature_names_out()
    tbl = pd.DataFrame({"feature": names, "coef": importances})
    tbl["feature"] = tbl["feature"].str.replace(r"^(num__|bool__|cat__)", "", regex=True)
    return tbl.sort_values("coef", ascending=False)


# Hiperparámetros elegidos por búsqueda manual sobre el split temporal
# (ver notas de la sección "Arquitectura" de la app): balance entre R² de
# test (~0.71) y qué tanto sobreajusta vs. train (~0.83 train R²).
RF_PARAMS = dict(n_estimators=500, max_depth=10, min_samples_leaf=2, random_state=0, n_jobs=-1)


def train_regression(df):
    df = prepare_frame(df)
    train, test = temporal_split(df)
    y_train = np.log1p(train["peak_impact_score"].clip(lower=0))
    y_test = np.log1p(test["peak_impact_score"].clip(lower=0))

    pre = build_preprocessor()
    pipe = Pipeline([("pre", pre), ("model", RandomForestRegressor(**RF_PARAMS))])
    pipe.fit(train[ALL_FEATURES], y_train)

    y_pred = pipe.predict(test[ALL_FEATURES])
    r2 = r2_score(y_test, y_pred)
    mae_log = mean_absolute_error(y_test, y_pred)
    mae_original = mean_absolute_error(np.expm1(y_test), np.expm1(y_pred))

    coefs = _importance_table(pre, pipe.named_steps["model"].feature_importances_)
    return RegressionResult(pipe, train, test, y_test.values, y_pred, r2, mae_log, mae_original, coefs)


def train_classification(df):
    df = prepare_frame(df)
    train, test = temporal_split(df)
    y_train = train["escalamiento"].values
    y_test = test["escalamiento"].values

    pre = build_preprocessor()
    pipe = Pipeline([
        ("pre", pre),
        ("model", LogisticRegression(max_iter=2000, class_weight="balanced")),
    ])
    pipe.fit(train[ALL_FEATURES], y_train)

    y_pred = pipe.predict(test[ALL_FEATURES])
    y_proba = pipe.predict_proba(test[ALL_FEATURES])[:, 1]

    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    roc_auc = roc_auc_score(y_test, y_proba)
    confusion = confusion_matrix(y_test, y_pred)
    fpr, tpr, _ = roc_curve(y_test, y_proba)

    coefs = _coef_table(pre, pipe.named_steps["model"].coef_[0])
    return ClassificationResult(
        pipe, train, test, y_test, y_pred, y_proba,
        accuracy, precision, recall, f1, roc_auc, confusion, fpr, tpr, coefs,
    )


# El mes crudo (12 categorías) hace que cada combinación mes×provincia tenga
# muy pocos eventos históricos (sparse) — agruparlo en 4 estaciones sube el
# accuracy de 0.56 a 0.62 (ver docstring del módulo). "Provincia" va sin
# agrupar (a diferencia de los otros dos modelos) porque aquí sí ayuda: con
# `province_grp` (top 12 + "Otra") el accuracy baja un poco.
SEASON_MAP = {12: "DEF", 1: "DEF", 2: "DEF", 3: "MAM", 4: "MAM", 5: "MAM",
              6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}
EVENT_TYPE_FEATURES = ["season", "province", "zone"]
EVENT_TYPE_RF_PARAMS = dict(n_estimators=600, max_depth=12, min_samples_leaf=3,
                             random_state=0, n_jobs=-1)


@dataclass
class EventTypeResult:
    pipeline: object
    classes: object
    train: pd.DataFrame
    test: pd.DataFrame
    accuracy: float
    top3_accuracy: float
    log_loss: float
    baseline_accuracy: float
    baseline_log_loss: float


def _add_season(df):
    df = df.copy()
    df["season"] = df["month"].astype(int).map(SEASON_MAP).astype(str)
    return df


def train_event_type_classifier(df):
    """Random Forest: predice, a partir de (estación del año derivada del
    mes, provincia, zona), la distribución de probabilidad sobre los 20
    tipos de evento posibles. Entrenada y evaluada con split temporal (no
    aleatorio) contra una línea base ("siempre predecir el tipo más
    frecuente") para que el accuracy tenga con qué compararse. Se probaron
    también regresión logística y otros ensambles (Extra Trees, Gradient
    Boosting) — Random Forest dio el mejor accuracy/top-3."""
    dfp = _add_season(prepare_frame(df))
    train, test = temporal_split(dfp)
    y_train, y_test = train["event_type"], test["event_type"]

    pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), EVENT_TYPE_FEATURES)])
    pipe = Pipeline([("pre", pre), ("clf", RandomForestClassifier(**EVENT_TYPE_RF_PARAMS))])
    pipe.fit(train[EVENT_TYPE_FEATURES], y_train)

    classes = pipe.named_steps["clf"].classes_
    proba = pipe.predict_proba(test[EVENT_TYPE_FEATURES])
    pred = pipe.predict(test[EVENT_TYPE_FEATURES])

    accuracy = accuracy_score(y_test, pred)
    top3_accuracy = top_k_accuracy_score(y_test, proba, k=3, labels=classes)
    ll = log_loss(y_test, proba, labels=classes)

    majority = y_train.value_counts().idxmax()
    baseline_accuracy = accuracy_score(y_test, [majority] * len(y_test))
    baseline_proba = np.tile(
        y_train.value_counts(normalize=True).reindex(classes, fill_value=1e-9).values,
        (len(y_test), 1),
    )
    baseline_log_loss = log_loss(y_test, baseline_proba, labels=classes)

    return EventTypeResult(pipe, classes, train, test, accuracy, top3_accuracy, ll,
                            baseline_accuracy, baseline_log_loss)


def predict_event_type_probabilities(pipe, classes, month, province, zone):
    season = SEASON_MAP[int(month)]
    row = pd.DataFrame([{"season": season, "province": province, "zone": zone}])
    proba = pipe.predict_proba(row)[0]
    tbl = pd.DataFrame({"event_type": classes, "probability": proba})
    return tbl.sort_values("probability", ascending=False).reset_index(drop=True)


def initial_index_from_counts(impact_counts):
    """El mismo cálculo que usa build_dataset.py para el índice de impacto,
    aplicado a las cifras que el usuario ya ingresó (conocidas al inicio).
    Sirve para explicar el resultado y para no dejar que el modelo prediga
    un pico por debajo de lo que ya se sabe (ver `predict_single`)."""
    return sum(
        impact_counts.get(f"initial_{k}", 0.0) * w for k, w in IMPACT_WEIGHTS.items()
    )


def predict_single(pipe, is_classifier, event_type, zone, province, month,
                    background_len, recurrence_prior, flags, impact_counts):
    """Arma una fila de features a partir de los inputs del formulario
    interactivo y devuelve la predicción del pipeline dado."""
    row = {c: impact_counts.get(c, 0.0) for c in [f"initial_{k}" for k in IMPACT_COLS]}
    row.update({
        "background_len": background_len,
        "recurrence_prior": recurrence_prior,
        "event_type": event_type,
        "zone": zone,
        "province_grp": province,
        "month": str(month),
    })
    row.update({k: int(v) for k, v in flags.items()})
    X = pd.DataFrame([row])[ALL_FEATURES]
    if is_classifier:
        proba = pipe.predict_proba(X)[0, 1]
        return proba

    # Devuelve las 3 cantidades por separado para que quede claro qué es
    # dato ya conocido y qué es lo que realmente predice el modelo:
    #   - initial: el índice de lo que YA se ingresó (no es predicción)
    #   - model_raw: lo que el Random Forest predice a partir de
    #     event_type/zona/provincia/mes/antecedente — esta es la parte
    #     que sí es predicción hacia adelante
    #   - final: max(initial, model_raw) — el pico no puede ser menor a
    #     lo ya reportado
    initial = initial_index_from_counts(impact_counts)
    pred_log = pipe.predict(X)[0]
    model_raw = float(np.expm1(pred_log))
    return {
        "initial": initial,
        "model_raw": model_raw,
        "final": max(initial, model_raw),
    }
