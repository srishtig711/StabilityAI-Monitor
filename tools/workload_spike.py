import argparse
import math
import multiprocessing
import time


def _positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def _spike_worker(stop_at, burst_seconds, rest_seconds):
    value = 0.0

    while time.time() < stop_at:
        burst_until = min(time.time() + burst_seconds, stop_at)
        while time.time() < burst_until:
            value += math.sin(value) * math.cos(value + 1)

        if time.time() < stop_at:
            time.sleep(rest_seconds)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create repeated CPU spikes for labeled monitoring data collection."
    )
    parser.add_argument("--duration", type=_positive_int, default=120, help="Run time in seconds.")
    parser.add_argument(
        "--workers",
        type=_positive_int,
        default=max(1, min(4, multiprocessing.cpu_count())),
        help="Number of spike worker processes.",
    )
    parser.add_argument("--burst", type=float, default=3.0, help="Busy period length in seconds.")
    parser.add_argument("--rest", type=float, default=4.0, help="Rest period length in seconds.")
    return parser.parse_args()


def main():
    args = parse_args()
    stop_at = time.time() + args.duration
    workers = [
        multiprocessing.Process(target=_spike_worker, args=(stop_at, args.burst, args.rest))
        for _ in range(args.workers)
    ]

    print(
        f"Spike workload running for {args.duration}s with {args.workers} worker(s), "
        f"{args.burst}s bursts and {args.rest}s rests."
    )
    print("Set the dashboard collection label to spike while this runs.")

    for worker in workers:
        worker.start()

    try:
        while time.time() < stop_at:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping spike workload early.")
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
            worker.join(timeout=3)

    print("Spike workload finished.")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
