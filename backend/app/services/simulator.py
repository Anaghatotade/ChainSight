"""
What-If Simulator
==================
Runs a deterministic (fixed-seed) discrete-day inventory simulation twice --
once under baseline parameters, once under the user's scenario parameters --
using the *same* underlying demand realization so the comparison isolates
the effect of the changed levers (demand, lead time, capacity, safety stock,
cost) rather than random noise.

Policy simulated: periodic review (weekly), order-up-to level.
"""
import math
from datetime import date, timedelta

import numpy as np


def _simulate(days, start_date, avg_demand, std_demand, lead_time_mean, lead_time_std,
              safety_stock, reorder_point, order_up_to, unit_cost, capacity_per_order, seed):
    rng = np.random.default_rng(seed)
    demand_series = np.clip(rng.normal(avg_demand, std_demand, size=days), 0, None)

    on_hand = order_up_to
    in_transit = 0
    pending = {}
    timeline = []
    total_procurement_cost = 0.0
    stockout_days = 0
    total_demand = 0.0
    total_fulfilled = 0.0

    review_period = 7
    for day in range(days):
        d = start_date + timedelta(days=day)
        todays_demand = float(demand_series[day])

        if day in pending:
            on_hand += pending.pop(day)

        fulfilled = min(on_hand, todays_demand)
        stockout = fulfilled < todays_demand - 1e-6
        on_hand -= fulfilled
        total_demand += todays_demand
        total_fulfilled += fulfilled
        if stockout:
            stockout_days += 1

        inv_position = on_hand + in_transit
        if day % review_period == 0 and inv_position < reorder_point:
            desired_qty = max(order_up_to - inv_position, avg_demand * review_period)
            order_qty = min(desired_qty, capacity_per_order) if capacity_per_order else desired_qty
            lead = max(1, int(round(rng.normal(lead_time_mean, max(lead_time_std, 0.1)))))
            arrival_day = day + lead
            if arrival_day < days:
                pending[arrival_day] = pending.get(arrival_day, 0) + order_qty
            in_transit += order_qty
            total_procurement_cost += order_qty * unit_cost

        service_level_so_far = (total_fulfilled / total_demand) if total_demand > 0 else 1.0
        timeline.append(dict(
            day=day, date=d, projected_on_hand=round(max(on_hand, 0), 1),
            projected_demand=round(todays_demand, 1), stockout=stockout,
            service_level=round(service_level_so_far, 4),
        ))

    overall_service_level = (total_fulfilled / total_demand) if total_demand > 0 else 1.0
    return dict(
        timeline=timeline,
        stockout_days=stockout_days,
        service_level=round(overall_service_level, 4),
        procurement_cost=round(total_procurement_cost, 2),
        avg_on_hand=round(float(np.mean([t["projected_on_hand"] for t in timeline])), 1),
        stockout_rate=round(stockout_days / days, 4),
    )


def run_simulation(
    sku: str,
    avg_demand: float, std_demand: float,
    lead_time_mean: float, lead_time_std: float,
    safety_stock: int, reorder_point: int, unit_cost: float,
    warehouse_capacity: int,
    demand_change_pct: float, lead_time_change_days: float,
    supplier_capacity_change_pct: float, safety_stock_change_units: int,
    cost_change_pct: float, simulation_days: int = 90,
):
    seed = abs(hash(sku)) % (2 ** 31)
    start_date = date.today()
    order_up_to_baseline = reorder_point + avg_demand * 10

    baseline = _simulate(
        simulation_days, start_date, avg_demand, std_demand,
        lead_time_mean, lead_time_std, safety_stock, reorder_point,
        order_up_to_baseline, unit_cost, capacity_per_order=None, seed=seed,
    )

    scenario_avg_demand = max(0.1, avg_demand * (1 + demand_change_pct / 100))
    scenario_std_demand = max(0.05, std_demand * (1 + max(demand_change_pct, 0) / 150))
    scenario_lead_time = max(1, lead_time_mean + lead_time_change_days)
    scenario_safety_stock = max(0, safety_stock + safety_stock_change_units)
    scenario_reorder_point = max(0, reorder_point + safety_stock_change_units)
    scenario_unit_cost = unit_cost * (1 + cost_change_pct / 100)
    scenario_order_up_to = scenario_reorder_point + scenario_avg_demand * 10

    capacity_per_order = None
    if supplier_capacity_change_pct != 0:
        baseline_typical_order = avg_demand * 7 + (order_up_to_baseline - reorder_point)
        capacity_per_order = max(1.0, baseline_typical_order * (1 + supplier_capacity_change_pct / 100))

    scenario = _simulate(
        simulation_days, start_date, scenario_avg_demand, scenario_std_demand,
        scenario_lead_time, lead_time_std, scenario_safety_stock, scenario_reorder_point,
        scenario_order_up_to, scenario_unit_cost, capacity_per_order=capacity_per_order, seed=seed,
    )

    delta = dict(
        service_level_pp=round((scenario["service_level"] - baseline["service_level"]) * 100, 2),
        stockout_days_diff=scenario["stockout_days"] - baseline["stockout_days"],
        procurement_cost_diff=round(scenario["procurement_cost"] - baseline["procurement_cost"], 2),
        procurement_cost_pct=round(
            ((scenario["procurement_cost"] - baseline["procurement_cost"]) / baseline["procurement_cost"] * 100)
            if baseline["procurement_cost"] > 0 else 0, 2),
        avg_on_hand_diff=round(scenario["avg_on_hand"] - baseline["avg_on_hand"], 1),
    )

    narrative = []
    if delta["service_level_pp"] < -1:
        narrative.append(f"Service level would drop by {abs(delta['service_level_pp'])} percentage points, "
                          f"risking {scenario['stockout_days']} stockout days over the {simulation_days}-day horizon "
                          f"(vs {baseline['stockout_days']} at baseline).")
    elif delta["service_level_pp"] > 1:
        narrative.append(f"Service level would improve by {delta['service_level_pp']} percentage points, "
                          f"reducing stockout days from {baseline['stockout_days']} to {scenario['stockout_days']}.")
    else:
        narrative.append("Service level stays roughly stable under this scenario.")

    if delta["procurement_cost_pct"] > 1:
        narrative.append(f"Procurement cost over the horizon increases by {delta['procurement_cost_pct']}% "
                          f"(+${delta['procurement_cost_diff']:,.0f}).")
    elif delta["procurement_cost_pct"] < -1:
        narrative.append(f"Procurement cost decreases by {abs(delta['procurement_cost_pct'])}% "
                          f"(-${abs(delta['procurement_cost_diff']):,.0f}).")

    if supplier_capacity_change_pct < 0 and delta["service_level_pp"] < -0.5:
        narrative.append(f"Reduced supplier capacity ({supplier_capacity_change_pct}%) constrains order sizes, "
                          f"which is a key driver of the increased stockout risk.")
    if lead_time_change_days > 0 and delta["service_level_pp"] < -0.5:
        narrative.append(f"An additional {lead_time_change_days:.0f} lead-time days increases the exposure window "
                          f"during which demand variability can cause a stockout.")
    elif lead_time_change_days > 0:
        narrative.append(f"An additional {lead_time_change_days:.0f} lead-time days lengthens the exposure window, "
                          f"though other changes in this scenario offset the effect on service level.")
    if safety_stock_change_units > 0:
        narrative.append(f"The extra {safety_stock_change_units} units of safety stock buffers against demand "
                          f"variability but ties up additional working capital.")
    elif safety_stock_change_units < 0:
        narrative.append(f"Cutting safety stock by {abs(safety_stock_change_units)} units frees working capital "
                          f"but reduces the buffer against demand spikes.")

    return dict(
        baseline=baseline, scenario=scenario, delta=delta, narrative=narrative,
    )
