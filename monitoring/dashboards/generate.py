#!/usr/bin/env python3
"""Generates quickbook-overview.json (Grafana dashboard). Edit here, then re-run:
    python3 monitoring/dashboards/generate.py
"""
import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
NS = 'namespace="quickbook"'
APP_HANDLERS = 'handler!~"/health|/ready|/metrics"'  # ignore probe/scrape traffic
NODE_NAME = " * on (instance) group_left (nodename) node_uname_info"  # adds the node's hostname as a label
# Pod name -> app name ("auth-service-5f9bc657b4-wcxmt" -> "auth-service", "postgres-0" -> "postgres"),
# so graphs stay readable after deploys instead of piling up old pod names.
POD_TO_APP = r'"app", "$1", "pod", "(.+?)(-[a-z0-9]{6,10}-[a-z0-9]{5}|-[0-9]+)$"'


def by_app(expr):
    return f"sum by (app) (label_replace({expr}, {POD_TO_APP}))"

panels, next_id, y = [], 1, 0


def add(panel, w, h, x, ds=DS):
    global next_id
    panel.update(id=next_id, datasource=ds, gridPos={"x": x, "y": y, "w": w, "h": h})
    panels.append(panel)
    next_id += 1


def row(title):
    global y, next_id
    panels.append({"type": "row", "title": title, "id": next_id, "collapsed": False,
                   "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []})
    next_id += 1
    y += 1


def targets(*exprs, ds=DS):
    return [{"refId": chr(65 + i), "expr": e, "legendFormat": l, "datasource": ds} for i, (e, l) in enumerate(exprs)]


def stat(title, expr, unit="short", color="blue", desc=""):
    return {"type": "stat", "title": title, "description": desc, "targets": targets((expr, "")),
            "fieldConfig": {"defaults": {"unit": unit, "decimals": 0, "color": {"mode": "fixed", "fixedColor": color}},
                            "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "none"}}


def series(title, *exprs, unit="short", stack=False, desc="", ds=DS):
    return {"type": "timeseries", "title": title, "description": desc, "targets": targets(*exprs, ds=ds),
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
     "fieldConfig": {"defaults": {"min": 0, "max": 2, "unit": "short", "color": {"mode": "thresholds"},
                                  "thresholds": {"mode": "absolute", "steps": [
         {"color": "red", "value": None}, {"color": "orange", "value": 1}, {"color": "green", "value": 2}]}},
                     "overrides": []},
     "options": {"orientation": "horizontal", "displayMode": "basic", "showUnfilled": True,
                 "reduceOptions": {"calcs": ["lastNotNull"]}}}, 12, 8, 12)
y += 4
add(series("Restarts per service (10m)",
           (by_app(f'increase(kube_pod_container_status_restarts_total{{{NS}}}[10m])'), "{{app}}")), 12, 4, 0)
y += 4
add(series("auth pods (HPA): current vs desired",
           (f'kube_horizontalpodautoscaler_status_current_replicas{{{NS},horizontalpodautoscaler="auth-service"}}', "current"),
           (f'kube_horizontalpodautoscaler_status_desired_replicas{{{NS},horizontalpodautoscaler="auth-service"}}', "desired"),
           (f'kube_horizontalpodautoscaler_spec_max_replicas{{{NS},horizontalpodautoscaler="auth-service"}}', "max"),
           desc="The HorizontalPodAutoscaler adds auth pods when average CPU > 70% of the 400m request."), 12, 6, 0)
add(series("Load shedding: requests rejected fast (503/s)",
           (f'sum(rate(quickbook_requests_shed_total{{{NS}}}[$__rate_interval]))', "shed 503/s"),
           (f'sum(quickbook_requests_in_flight{{{NS}}})', "in flight (auth, all pods)"),
           desc="Beyond 18 requests in flight per auth pod, extra requests get an immediate 503 instead of a 30 s timeout."),
    12, 6, 12)
y += 6
add(series("CPU per service (cores, all replicas)",
           (by_app(f'rate(container_cpu_usage_seconds_total{{{NS},container!="",container!="POD"}}[$__rate_interval])'),
            "{{app}}"), unit="short", stack=True), 12, 8, 0)
add(series("Memory per service (all replicas)",
           (by_app(f'container_memory_working_set_bytes{{{NS},container!="",container!="POD"}}'), "{{app}}"),
           unit="bytes", stack=True), 12, 8, 12)
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

# ---------------- Logs (Loki) ----------------
row("Logs (Loki)")
LOG_SELECTOR = '{namespace="quickbook", app=~"$app"}'
add(series("Log lines per service",
           (f'sum by (app) (count_over_time({LOG_SELECTOR} [$__interval]))', "{{app}}"),
           stack=True, ds=LOKI), 12, 8, 0, ds=LOKI)
add(series("Errors & warnings per service",
           ('sum by (app, level) (count_over_time({namespace="quickbook", app=~"$app", level=~"ERROR|WARNING"} [$__interval]))',
            "{{app}} {{level}}"),
           stack=True, ds=LOKI, desc="From the JSON 'level' field the services log."), 12, 8, 12, ds=LOKI)
panels[-1]["fieldConfig"]["defaults"]["noValue"] = "No errors or warnings"
y += 8
# JSON service logs are reformatted into one readable line; other lines (nginx, postgres) are shown as-is.
LOG_FORMAT = ('{{if .service}}[{{.service}}] {{.message}}'  # level is shown by Grafana's own level column
              '{{if .path}}  {{.method}} {{.path}} → {{.status}} ({{.duration_ms}} ms){{end}}'
              '{{else}}{{__line__}}{{end}}')
add({"type": "logs", "title": "QuickBook logs (filter with the app / search boxes at the top)",
     "targets": targets((f'{LOG_SELECTOR} |= "$search" | json | drop __error__, __error_details__ | line_format `{LOG_FORMAT}`', ""), ds=LOKI),
     "options": {"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending",
                 "enableLogDetails": True, "prettifyLogMessage": False, "dedupStrategy": "none"}},
    24, 12, 0, ds=LOKI)
y += 12

APPS = ["auth-service", "inventory-service", "booking-service", "payment-service", "ticket-service", "frontend", "postgres"]
templating = {"list": [
    {"type": "custom", "name": "app", "label": "app (logs)", "query": ",".join(APPS),
     "multi": True, "includeAll": True, "allValue": ".*",
     "current": {"text": ["All"], "value": ["$__all"]},
     "options": [{"text": "All", "value": "$__all", "selected": True}] + [{"text": a, "value": a, "selected": False} for a in APPS]},
    {"type": "textbox", "name": "search", "label": "search logs", "query": "",
     "current": {"text": "", "value": ""}},
]}

dashboard = {
    "uid": "quickbook-overview", "title": "QuickBook Overview", "tags": ["quickbook"],
    "timezone": "browser", "schemaVersion": 39, "refresh": "30s",
    "time": {"from": "now-1h", "to": "now"}, "panels": panels, "templating": templating,
}
out = Path(__file__).with_name("quickbook-overview.json")
out.write_text(json.dumps(dashboard, indent=2) + "\n")
print(f"wrote {out} ({len(panels)} panels)")
