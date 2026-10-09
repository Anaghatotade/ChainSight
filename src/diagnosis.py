"""
diagnosis.py - bias / variance diagnosis using a baseline as the "human-level proxy".

From "Structuring Machine Learning Projects":
    avoidable bias = training error - human-level error     (can the model even fit the training data well?)
    variance       = dev error      - training error         (does it fall apart on new data?)
Here 'human-level' is replaced by the best simple baseline (Naive / Moving average / Exp. smoothing),
because that is what a planner would do without any model.
"""


def diagnose(proxy_error, train_error, dev_error):
    avoidable_bias = train_error - proxy_error
    variance = dev_error - train_error
    if avoidable_bias <= 0 and variance <= 0.02:
        text = ("The model already beats the baseline proxy on the training weeks and generalises: "
                "bias and variance are both small. Remaining error is likely noise or information these features do not contain.")
    elif avoidable_bias <= 0:
        text = ("The model beats the proxy on training weeks (no avoidable bias) but dev error is higher than train error: "
                "VARIANCE is the main issue -> more data, stronger regularisation, fewer/simpler features.")
    elif avoidable_bias > variance:
        text = ("AVOIDABLE BIAS dominates: even on training weeks the model is worse than the baseline proxy "
                "-> richer features or a bigger model, longer training.")
    else:
        text = ("VARIANCE dominates: the model fits the training weeks but does worse on dev "
                "-> more data, regularisation (L2/dropout), simpler model.")
    return dict(proxy_error=proxy_error, train_error=train_error, dev_error=dev_error,
                avoidable_bias=avoidable_bias, variance=variance, diagnosis=text)
