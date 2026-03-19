#!/usr/bin/env python3
"""
BMO Power Measurement Tool
Per AI Council recommendation: "Measure before optimizing"

Measures power consumption for different wake word configurations:
- Continuous wake word detection (Option A)
- VAD-first approach (Option B - for comparison)

Requirements:
- USB power meter hardware (e.g., UM25C, YZXstudio, etc.)
- Access to power meter serial interface
OR
- Manual recording mode (logs timestamps for manual meter readings)

Usage:
    # Automated with USB power meter
    sudo python3 measure_power.py --meter /dev/ttyUSB0 --duration 3600

    # Manual recording (user reads power meter every minute)
    python3 measure_power.py --manual --duration 3600
"""

import argparse
import time
import datetime
import json
import subprocess
import sys
from pathlib import Path

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("Warning: psutil not installed. CPU/memory tracking limited.")


class PowerMeasurement:
    """Tracks power consumption over time."""

    def __init__(self, test_name: str, duration_seconds: int):
        self.test_name = test_name
        self.duration = duration_seconds
        self.measurements = []
        self.start_time = None
        self.end_time = None
        self.test_conditions = {}

    def add_measurement(self, timestamp: float, watts: float, volts: float = None, amps: float = None):
        """Add a power measurement."""
        self.measurements.append({
            'timestamp': timestamp,
            'elapsed': timestamp - self.start_time if self.start_time else 0,
            'watts': watts,
            'volts': volts,
            'amps': amps
        })

    def add_manual_measurement(self, watts: float):
        """Add a manual measurement (uses current time)."""
        timestamp = time.time()
        self.add_measurement(timestamp, watts)

    def start(self):
        """Start measurement session."""
        self.start_time = time.time()
        print(f"[MEASUREMENT] Started: {self.test_name}")
        print(f"[MEASUREMENT] Duration: {self.duration}s ({self.duration/60:.1f} minutes)")

    def finish(self):
        """Finish measurement and calculate statistics."""
        self.end_time = time.time()
        actual_duration = self.end_time - self.start_time
        print(f"[MEASUREMENT] Finished after {actual_duration:.0f}s")

    def calculate_stats(self) -> dict:
        """Calculate power consumption statistics."""
        if not self.measurements:
            return {}

        watts = [m['watts'] for m in self.measurements if m['watts'] is not None]
        if not watts:
            return {}

        avg_watts = sum(watts) / len(watts)
        max_watts = max(watts)
        min_watts = min(watts)

        # Calculate energy consumption (Wh)
        actual_duration_hours = (self.end_time - self.start_time) / 3600
        watt_hours = avg_watts * actual_duration_hours

        # Project to 24 hours
        watt_hours_per_day = avg_watts * 24

        # Convert to mAh (assuming 5V USB power)
        VOLTAGE = 5.0
        mah_consumed = (watt_hours / VOLTAGE) * 1000
        mah_per_day = (watt_hours_per_day / VOLTAGE) * 1000

        # Battery life projection (10,000mAh battery)
        BATTERY_CAPACITY_MAH = 10000
        battery_life_hours = BATTERY_CAPACITY_MAH / (avg_watts / VOLTAGE * 1000) if avg_watts > 0 else 0

        return {
            'test_name': self.test_name,
            'duration_seconds': self.end_time - self.start_time,
            'sample_count': len(self.measurements),
            'avg_watts': avg_watts,
            'max_watts': max_watts,
            'min_watts': min_watts,
            'watt_hours': watt_hours,
            'watt_hours_per_day': watt_hours_per_day,
            'mah_consumed': mah_consumed,
            'mah_per_day': mah_per_day,
            'projected_battery_life_hours': battery_life_hours,
            'test_conditions': self.test_conditions
        }

    def save_report(self, output_file: str = None):
        """Save measurement report to JSON file."""
        if output_file is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"power_measurement_{self.test_name}_{timestamp}.json"

        stats = self.calculate_stats()
        report = {
            'measurements': self.measurements,
            'statistics': stats
        }

        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"[REPORT] Saved to: {output_file}")
        return output_file

    def print_summary(self):
        """Print measurement summary to console."""
        stats = self.calculate_stats()
        if not stats:
            print("[SUMMARY] No measurements recorded")
            return

        print("\n" + "="*60)
        print(f"POWER MEASUREMENT SUMMARY: {self.test_name}")
        print("="*60)
        print(f"Duration:          {stats['duration_seconds']:.0f}s ({stats['duration_seconds']/60:.1f} min)")
        print(f"Samples:           {stats['sample_count']}")
        print(f"Average Power:     {stats['avg_watts']:.2f} W")
        print(f"Max Power:         {stats['max_watts']:.2f} W")
        print(f"Min Power:         {stats['min_watts']:.2f} W")
        print(f"Energy Consumed:   {stats['watt_hours']:.2f} Wh")
        print(f"Energy Per Day:    {stats['watt_hours_per_day']:.2f} Wh/day")
        print(f"mAh Consumed:      {stats['mah_consumed']:.0f} mAh")
        print(f"mAh Per Day:       {stats['mah_per_day']:.0f} mAh/day")
        print(f"Battery Life:      {stats['projected_battery_life_hours']:.1f} hours")
        print("="*60 + "\n")


def monitor_processes(test: PowerMeasurement):
    """Monitor CPU and memory usage of BMO processes."""
    if not HAS_PSUTIL:
        return

    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            if 'agent.py' in proc.info['name'] or 'openwakeword' in proc.info['name'].lower():
                test.test_conditions[f"process_{proc.info['name']}"] = {
                    'cpu_percent': proc.info['cpu_percent'],
                    'memory_percent': proc.info['memory_percent']
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def run_manual_measurement(test_name: str, duration: int):
    """Run manual power measurement (user reads power meter)."""
    test = PowerMeasurement(test_name, duration)
    test.start()

    print("\n" + "="*60)
    print("MANUAL MEASUREMENT MODE")
    print("="*60)
    print("Instructions:")
    print("1. Connect your USB power meter between battery and Pi")
    print("2. Read the power (watts) from the meter display")
    print("3. Enter the reading when prompted (press Enter to record)")
    print("4. Press Ctrl+C to stop early")
    print("="*60 + "\n")

    interval = 60  # Prompt every minute
    next_prompt = time.time() + interval

    try:
        while time.time() - test.start_time < duration:
            if time.time() >= next_prompt:
                elapsed = int(time.time() - test.start_time)
                remaining = duration - elapsed

                print(f"\n[{elapsed}s / {duration}s] ({remaining}s remaining)")
                try:
                    watts_str = input("Enter current power reading (watts): ")
                    watts = float(watts_str)
                    test.add_manual_measurement(watts)
                    print(f"  ✓ Recorded: {watts:.2f} W")
                except ValueError:
                    print("  ✗ Invalid input, skipped")

                next_prompt = time.time() + interval
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Stopping measurement...")

    test.finish()
    test.print_summary()
    test.save_report()


def run_automated_measurement(test_name: str, duration: int, meter_device: str):
    """Run automated power measurement with USB power meter."""
    print(f"[ERROR] Automated measurement not yet implemented")
    print(f"[ERROR] Requires specific USB power meter protocol implementation")
    print(f"[INFO] Use --manual mode instead")
    return


def check_wake_word_running() -> bool:
    """Check if wake word detection is currently running."""
    if not HAS_PSUTIL:
        return False

    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'agent.py' in cmdline or 'openwakeword' in cmdline.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Measure BMO power consumption",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Manual measurement for 1 hour (3600 seconds)
  python3 measure_power.py --manual --duration 3600 --name "continuous_wake_word"

  # Automated with USB power meter (if supported)
  python3 measure_power.py --meter /dev/ttyUSB0 --duration 7200

Test Configurations:
  1. Continuous wake word: Run agent.py normally, measure for 2+ hours
  2. VAD-first: Modify agent.py wake word config, measure for 2+ hours
  3. Idle baseline: Close agent.py, measure Pi 5 idle power
        """
    )

    parser.add_argument('--name', default='power_test',
                       help='Test name (e.g., "continuous_wake_word")')
    parser.add_argument('--duration', type=int, default=3600,
                       help='Measurement duration in seconds (default: 3600 = 1 hour)')
    parser.add_argument('--manual', action='store_true',
                       help='Manual measurement mode (user enters readings)')
    parser.add_argument('--meter', type=str,
                       help='USB power meter device (e.g., /dev/ttyUSB0)')

    args = parser.parse_args()

    # Check if agent.py is running
    if check_wake_word_running():
        print("[INFO] Detected agent.py running")
        print("[INFO] This measurement will include wake word power consumption")
    else:
        print("[WARNING] agent.py not detected")
        print("[WARNING] This will measure idle Pi power only")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(0)

    if args.manual:
        run_manual_measurement(args.name, args.duration)
    elif args.meter:
        run_automated_measurement(args.name, args.duration, args.meter)
    else:
        print("Error: Must specify --manual or --meter")
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
