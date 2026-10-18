"""Teste pentru modelul de semnal al simulatorului."""

from factorypulse.simulator import MACHINES, SignalGenerator


def test_same_seed_gives_same_series() -> None:
    machine, sensor = MACHINES[0], MACHINES[0].sensors[0]
    first = SignalGenerator(seed=7)
    second = SignalGenerator(seed=7)
    series_a = [first.sample(machine, sensor, t) for t in range(0, 100, 5)]
    series_b = [second.sample(machine, sensor, t) for t in range(0, 100, 5)]
    assert series_a == series_b


def test_values_stay_near_base_for_all_sensors() -> None:
    gen = SignalGenerator(seed=1)
    for machine in MACHINES:
        for sensor in machine.sensors:
            values = [gen.sample(machine, sensor, t) for t in range(0, 7200, 60)]
            # abatere maxima admisa: amplitudine sezoniera + 6 sigma zgomot
            limit = (
                sensor.seasonal_amplitude + 6 * sensor.noise_std + abs(sensor.trend_per_hour * 2)
            )
            assert all(abs(v - sensor.base) <= limit for v in values), (machine.name, sensor.name)


def test_seasonality_changes_value_over_period() -> None:
    gen = SignalGenerator(seed=3)
    machine = MACHINES[0]
    sensor = machine.sensors[0]
    # sin(pi/2) = 1 la un sfert de perioada; zgomotul e mult sub amplitudine
    quarter = sensor.period_s / 4
    peak = gen.sample(machine, sensor, quarter)
    trough = gen.sample(machine, sensor, 3 * quarter)
    assert peak - trough > sensor.seasonal_amplitude
