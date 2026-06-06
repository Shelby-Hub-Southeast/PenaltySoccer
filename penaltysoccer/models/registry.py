"""Model registry for the PenaltySoccer application layer."""

from __future__ import annotations

import penaltyblog as pb

DEFAULT_MODELS = ["dc", "poisson", "bivariate"]

MODEL_REGISTRY = {
    "dc": pb.models.DixonColesGoalModel,
    "poisson": pb.models.PoissonGoalsModel,
    "bivariate": pb.models.BivariatePoissonGoalModel,
    "negative_binomial": pb.models.NegativeBinomialGoalModel,
    "zero_inflated": pb.models.ZeroInflatedPoissonGoalsModel,
    "weibull_copula": pb.models.WeibullCopulaGoalsModel,
    "bayesian": pb.models.BayesianGoalModel,
    "hierarchical_bayesian": pb.models.HierarchicalBayesianGoalModel,
}

MODEL_DISPLAY_NAMES = {
    "dc": "Dixon-Coles",
    "poisson": "Poisson",
    "bivariate": "Bivariate Poisson",
    "negative_binomial": "Negative Binomial",
    "zero_inflated": "Zero-Inflated Poisson",
    "weibull_copula": "Weibull Copula",
    "bayesian": "Bayesian Goal Model",
    "hierarchical_bayesian": "Hierarchical Bayesian Goal Model",
}
