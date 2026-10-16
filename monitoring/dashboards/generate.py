#!/usr/bin/env python3
"""Generates quickbook-overview.json (Grafana dashboard). Edit here, then re-run:
    python3 monitoring/dashboards/generate.py
"""
import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "prometheus"}
NS = 'namespace="quickbook"'
APP_HANDLERS = 'handler!~"/health|/ready|/metrics"'  # ignore probe/scrape traffic
NODE_NAME = " * on (instance) group_left (nodename) node_uname_info"  # adds the node's hostname as a label

panels, next_id, y = [], 1, 0


def add(panel, w, h, x):
    global next_id
    panel.update(id=next_id, datasource=DS, gridPos={"x": x, "y": y, "w": w, "h": h})
    panels.append(panel)
    next_id += 1


def row(title):
    global y, next_id
    panels.append({"type": "row", "title": title, "id": next_id, "collapsed": False,
                   "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []})
    next_id += 1
    y += 1


def targets(*exprs):
    return [{"refId": chr(65 + i), "expr": e, "legendFormat": l, "datasource": DS} for i, (e, l) in enumerate(exprs)]


def stat(title, expr, unit="short", color="blue", desc=""):
    return {"type": "stat", "title": title, "description": desc, "targets": targets((expr, "")),
            "fieldConfig": {"defaults": {"unit": unit, "decimals": 0, "color": {"mode": "fixed", "fixedColor": color}},
                            "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "none"}}


def series(title, *exprs, unit="short", stack=False, desc=""):
    return {"type": "timeseries", "title": title, "description": desc, "targets": targets(*exprs),
            "fieldConfig": {"defaults": {"unit": unit, "custom": {
                "fillOpacity": 15, "lineWidth": 2, "showPoints": "never",
                "stacking": {"mode": "normal" if stack else "none"}}}, "overrides": []},
            "options": {"legend": {"displayMode": "table", "placement": "right", "calcs": ["lastNotNull", "max"]},
                        "tooltip": {"mode": "multi", "sort": "desc"}}}


# ---------------- Users & business ----------------
row("Users & business (selected time range)")
for i, (title, expr, unit, color) in enumerate([
    ("Registered users", "max(quickbook_registered_users)", "short", "purple"),
    ("Sign-ups", "sum(increase(quickbook_signups_total[$__range]))", "short", "blue"),
    ("Successful sign-ins", 'sum(increase(quickbook_signins_total{result="success"}[$__range]))', "short", "green"),
    ("Failed sign-ins", 'sum(increase(quickbook_signins_total{result="failure"}[$__range]))', "short", "orange"),
    ("Bookings confirmed", "sum(increase(quickbook_bookings_confirmed_total[$__range]))", "short", "green"),
    ("Revenue", "sum(increase(quickbook_revenue_inr_total[$__range]))", "currencyINR", "yellow"),
]):
    add(stat(title, expr, unit, color), 4, 4, i * 4)
y += 4
add(series("Booking funnel (per minute)",
           ('sum by (mode) (rate(quickbook_searches_total[$__rate_interval])) * 60', "searches {{mode}}"),
           ('sum by (mode) (rate(quickbook_bookings_created_total[$__rate_interval])) * 60', "created {{mode}}"),
           ('sum by (mode) (rate(quickbook_bookings_confirmed_total[$__rate_interval])) * 60', "confirmed {{mode}}"),
           desc="Searches -> bookings created -> bookings paid, split by flight/train."), 12, 8, 0)
add(series("Payments & tickets (per minute)",
           ('sum by (status) (rate(quickbook_payments_total[$__rate_interval])) * 60', "payment {{status}}"),
           ('sum(rate(quickbook_tickets_generated_total[$__rate_interval])) * 60', "tickets downloaded")), 12, 8, 12)
y += 8

# ---------------- Traffic ----------------
row("Traffic (HTTP, per service)")
add(series("Requests per second",
           (f'sum by (job) (rate(http_requests_total{{{NS},{APP_HANDLERS}}}[$__rate_interval]))', "{{job}}"),
           unit="reqps", stack=True), 12, 8, 0)
add(series("Error rate (5xx %)",
           # "or ... * 0" makes services with no 5xx show 0% instead of "No data".
           (f'100 * (sum by (job) (rate(http_requests_total{{{NS},status="5xx"}}[$__rate_interval]))'
            f' or sum by (job) (rate(http_requests_total{{{NS}}}[$__rate_interval])) * 0)'
            f' / sum by (job) (rate(http_requests_total{{{NS}}}[$__rate_interval]))', "{{job}}"),
           unit="percent", desc="Share of requests that failed with a server error."), 12, 8, 12)
y += 8
add(series("Latency p95",
           (f'histogram_quantile(0.95, sum by (job, le) (rate(http_request_duration_seconds_bucket{{{NS},{APP_HANDLERS}}}[$__rate_interval])))',
            "{{job}}"), unit="s", desc="95% of requests finished faster than this."), 12, 8, 0)
add(series("Responses by status class",
           (f'sum by (status) (rate(http_requests_total{{{NS},{APP_HANDLERS}}}[$__rate_interval]))', "{{status}}"),
           unit="reqps", stack=True), 12, 8, 12)
y += 8

# ---------------- Pods ----------------
row("Pods (namespace quickbook)")
add(stat("Running pods", f'sum(kube_pod_status_phase{{{NS},phase="Running"}})', color="green"), 4, 4, 0)
add(stat("Pods not ready", f'sum(kube_pod_status_ready{{{NS},condition="false"}}) or vector(0)', color="red",
         desc="Pods failing their readiness probe (not receiving traffic)."), 4, 4, 4)
add(stat("Restarts (selected range)",
         f'sum(increase(kube_pod_container_status_restarts_total{{{NS}}}[$__range]))', color="orange"), 4, 4, 8)
add({"type": "bargauge", "title": "Available replicas per deployment",
     "targets": targets((f'kube_deployment_status_replicas_available{{{NS}}}', "{{deployment}}")),
     "fieldConfig": {"defaults": {"min": 0, "max": 3, "unit": "short", "thresholds": {"mode": "absolute", "steps": [
         {"color": "red", "value": None}, {"color": "orange", "value": 1}, {"color": "green", "value": 2}]}},
                     "overrides": []},
     "options": {"orientation": "horizontal", "displayMode": "gradient",
                 "reduceOptions": {"calcs": ["lastNotNull"]}}}, 12, 8, 12)
y += 4
add(series("Pod restarts", (f'sum by (pod) (increase(kube_pod_container_status_restarts_total{{{NS}}}[10m]))', "{{pod}}")),
    12, 4, 0)
y += 4
add(series("CPU per pod (cores)",
           (f'sum by (pod) (rate(container_cpu_usage_seconds_total{{{NS},container!="",container!="POD"}}[$__rate_interval]))',
            "{{pod}}"), unit="short"), 12, 8, 0)
add(series("Memory per pod",
           (f'sum by (pod) (container_memory_working_set_bytes{{{NS},container!="",container!="POD"}})', "{{pod}}"),
           unit="bytes"), 12, 8, 12)
y += 8

# ---------------- Nodes ----------------
row("Cluster nodes")
add(series("Node CPU used",
           ('100 * (1 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[$__rate_interval])))' + NODE_NAME, "{{nodename}}"),
           unit="percent"), 8, 8, 0)
add(series("Node memory used",
           ("100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)" + NODE_NAME, "{{nodename}}"),
           unit="percent"), 8, 8, 8)
add(series("Node disk used (/)",
           ('100 * (1 - node_filesystem_avail_bytes{mountpoint="/",fstype!="tmpfs"}'
            ' / node_filesystem_size_bytes{mountpoint="/",fstype!="tmpfs"})' + NODE_NAME, "{{nodename}}"),
           unit="percent"), 8, 8, 16)
y += 8

dashboard = {
    "uid": "quickbook-overview", "title": "QuickBook Overview", "tags": ["quickbook"],
    "timezone": "browser", "schemaVersion": 39, "refresh": "30s",
    "time": {"from": "now-1h", "to": "now"}, "panels": panels,
}
out = Path(__file__).with_name("quickbook-overview.json")
out.write_text(json.dumps(dashboard, indent=2) + "\n")
print(f"wrote {out} ({len(panels)} panels)")
