"""Shared capacity rules for the web worker and standalone daemon."""


class WorkerCapacityError(RuntimeError):
    pass


def worker_capacity_error(registry, owner, active_count):
    limits = registry.user_limits(owner)
    if active_count() >= limits["worker_default"]:
        return "Slot worker penuh. Hentikan salah satu akun dulu."
    override = limits["worker_override"]
    if override is not None and active_count(owner) >= override:
        return "Batas worker pengguna tercapai. Hentikan worker dari salah satu akunnya dulu."
    return None
