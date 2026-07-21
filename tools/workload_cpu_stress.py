import argparse
import math
import multiprocessing
import time


def _positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def _bounded_percent(value):
    parsed = int(value)
    if parsed < 1 or parsed > 100:
        raise argparse.ArgumentTypeError("value must be between 1 and 100")
    return parsed


def _cpu_worker(stop_at, duty_cycle):
    active_seconds = duty_cycle / 100
    idle_seconds = 1 - active_seconds
    value = 0.0

    while time.time() < stop_at:
        active_until = time.time() + active_seconds
        while time.time() < active_until:
            value += math.sqrt((value % 1000) + 1)

        if idle_seconds > 0:
            time.sleep(idle_seconds)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create repeatable CPU pressure for labeled monitoring data collection."
    )
    parser.add_argument("--duration", type=_positive_int, default=120, help="Run time in seconds.")
    parser.add_argument(
        "--workers",
        type=_positive_int,
        default=max(1, min(4, multiprocessing.cpu_count())),
        help="Number of CPU worker processes.",
    )
    parser.add_argument(
        "--duty-cycle",
        type=_bounded_percent,
        default=90,
        help="CPU busy percentage per one-second cycle.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    stop_at = time.time() + args.duration
    workers = [
        multiprocessing.Process(target=_cpu_worker, args=(stop_at, args.duty_cycle))
        for _ in range(args.workers)
    ]

    print(
        f"CPU stress running for {args.duration}s with {args.workers} worker(s) "
        f"at {args.duty_cycle}% duty cycle."
    )
    print("Set the dashboard collection label to cpu_stress while this runs.")

    for worker in workers:
        worker.start()

    try:
        while time.time() < stop_at:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping CPU stress early.")
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
            worker.join(timeout=3)

    print("CPU stress finished.")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
