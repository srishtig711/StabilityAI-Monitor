import argparse
import time


def _positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create gradual memory pressure for labeled monitoring data collection."
    )
    parser.add_argument("--duration", type=_positive_int, default=120, help="Run time in seconds.")
    parser.add_argument(
        "--target-mb",
        type=_positive_int,
        default=512,
        help="Approximate memory to hold in MB.",
    )
    parser.add_argument(
        "--step-mb",
        type=_positive_int,
        default=32,
        help="Memory allocated per step in MB.",
    )
    parser.add_argument(
        "--step-delay",
        type=float,
        default=1.0,
        help="Seconds to wait between allocation steps.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    blocks = []
    allocated_mb = 0
    stop_at = time.time() + args.duration

    print(
        f"Memory pressure running for {args.duration}s, growing toward "
        f"{args.target_mb} MB in {args.step_mb} MB steps."
    )
    print("Set the dashboard collection label to memory_pressure while this runs.")

    try:
        while time.time() < stop_at:
            if allocated_mb < args.target_mb:
                next_step = min(args.step_mb, args.target_mb - allocated_mb)
                blocks.append(bytearray(next_step * 1024 * 1024))
                allocated_mb += next_step
                print(f"Allocated approximately {allocated_mb} MB.")

            time.sleep(max(args.step_delay, 0.1))
    except KeyboardInterrupt:
        print("Stopping memory pressure early.")
    finally:
        blocks.clear()

    print("Memory pressure finished.")


if __name__ == "__main__":
    main()
