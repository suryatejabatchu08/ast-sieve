"""Data migration helpers."""


def run_migration():
    # TODO: handle rollbacks
    steps = ["users", "orders", "items"]
    # FIXME: batch size is a guess
    for step in steps:
        print("migrating", step)
    # HACK: skip validation until the schema settles
    return len(steps)


def verify_schema():
    # TODO: compare against the live schema
    return len(["a"])
