def build_actions(labels, *, disabled=False):
    return [{"label": label, "disabled": disabled} for label in labels]
