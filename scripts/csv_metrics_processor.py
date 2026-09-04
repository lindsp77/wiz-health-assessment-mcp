"""
CSV Metrics Processor for Wiz Health Assessment Suite.

Provides:
- export_metrics_to_csv: Exports populated metrics to a structured CSV file.
- generate_intake_template_csv: Generates a blank, annotated intake CSV to request from customers.
- load_metrics_from_csv: Loads and normalizes metrics from a customer-filled CSV for deck generation.
"""

import csv
import io
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


METRIC_DEFINITIONS: List[Dict[str, Any]] = [
    # --- Header & General ---
    {"var": "CUSTOMER", "category": "General", "name": "Customer Name", "slide": "1, 14", "desc": "Customer organization or tenant name", "default": "Customer"},
    {"var": "TAM_NAME", "category": "General", "name": "Technical Account Manager", "slide": "1", "desc": "Assigned Wiz TAM / Architect", "default": ""},
    {"var": "DATE", "category": "General", "name": "Assessment Date", "slide": "1, 14", "desc": "Date of Health Assessment (YYYY-MM-DD)", "default": ""},

    # --- Cloud Architecture & AI Footprint (Slide 3) ---
    {"var": "C_AWS", "category": "Cloud Architecture", "name": "AWS Accounts Count", "slide": "3", "desc": "Total connected AWS accounts", "default": "0"},
    {"var": "C_AZ", "category": "Cloud Architecture", "name": "Azure Subscriptions Count", "slide": "3", "desc": "Total connected Azure subscriptions", "default": "0"},
    {"var": "C_GCP", "category": "Cloud Architecture", "name": "GCP Projects Count", "slide": "3", "desc": "Total connected GCP projects", "default": "0"},
    {"var": "C_OTH", "category": "Cloud Architecture", "name": "Other Cloud Accounts Count", "slide": "3", "desc": "OCI, Alibaba, etc.", "default": "0"},
    {"var": "C_OTH_NAMES", "category": "Cloud Architecture", "name": "Other Cloud Provider Names", "slide": "3", "desc": "Names of other cloud providers", "default": ""},
    {"var": "CON_TOT", "category": "Cloud Architecture", "name": "Total Connected Connectors", "slide": "3", "desc": "Total connectors across all types", "default": "0"},
    {"var": "AI_AGENTS_COUNT", "category": "AI Footprint", "name": "AI Agents Discovered", "slide": "3", "desc": "Active AI Agent entities", "default": "0"},
    {"var": "AI_MODELS_COUNT", "category": "AI Footprint", "name": "AI Models Discovered", "slide": "3", "desc": "Active AI Model entities", "default": "0"},
    {"var": "AI_GUARDRAILS_COUNT", "category": "AI Footprint", "name": "AI Guardrails Discovered", "slide": "3", "desc": "Active AI Guardrail entities", "default": "0"},
    {"var": "AI_MCP_SERVERS_COUNT", "category": "AI Footprint", "name": "MCP Servers Discovered", "slide": "3", "desc": "Model Context Protocol servers", "default": "0"},
    {"var": "AI_PIPELINES_COUNT", "category": "AI Footprint", "name": "AI Pipelines Discovered", "slide": "3", "desc": "Active AI Pipelines", "default": "0"},
    {"var": "AI_DATASETS_COUNT", "category": "AI Footprint", "name": "AI Datasets Discovered", "slide": "3", "desc": "AI Datastores / Training sets", "default": "0"},
    {"var": "AI_TECHNOLOGIES_COUNT", "category": "AI Footprint", "name": "AI Technologies Count", "slide": "3", "desc": "AI libraries & frameworks (PyTorch, TensorFlow, etc.)", "default": "0"},
    {"var": "AI_CA_COUNT", "category": "AI Footprint", "name": "AI Coding Agents (IDEs)", "slide": "3", "desc": "Developer IDEs with AI assistants", "default": "0"},
    {"var": "AI_CODE_REPOS_COUNT", "category": "AI Footprint", "name": "AI Code Repositories", "slide": "3", "desc": "VCS repositories using AI technologies", "default": "0"},
    {"var": "AI_WORKLOADS_COUNT", "category": "AI Footprint", "name": "AI Running Workloads", "slide": "3", "desc": "Workloads executing AI models or pipelines", "default": "0"},

    # --- Workloads & Compute Inventory (Slide 3 & 4) ---
    {"var": "WS_T", "category": "Workload Inventory", "name": "Total Compute Workload Scans", "slide": "4", "desc": "Total compute workload scans evaluated", "default": "0"},
    {"var": "WS_F", "category": "Workload Inventory", "name": "Workload Scans Failed", "slide": "4", "desc": "Failed workload scans", "default": "0"},
    {"var": "WS_SK", "category": "Workload Inventory", "name": "Workload Scans Skipped", "slide": "4", "desc": "Skipped workload scans", "default": "0"},
    {"var": "WS_P", "category": "Workload Inventory", "name": "Workload Scan Success Ratio %", "slide": "4", "desc": "Success ratio for compute workload scans", "default": "100%"},
    {"var": "SERVERLESS_FN_COUNT", "category": "Workload Inventory", "name": "Serverless Functions Count", "slide": "3", "desc": "Lambda, Azure Functions, Cloud Run", "default": "0"},
    {"var": "SERVERLESS_CT_COUNT", "category": "Workload Inventory", "name": "Serverless Containers Count", "slide": "3", "desc": "Fargate, Cloud Run container instances", "default": "0"},
    {"var": "R_TOT", "category": "Workload Inventory", "name": "Container Registries Count", "slide": "3, 4", "desc": "ECR, ACR, GCR, GAR registries", "default": "0"},
    {"var": "K8S", "category": "Workload Inventory", "name": "Kubernetes Clusters Count", "slide": "3, 4", "desc": "Total managed & self-hosted K8s clusters", "default": "0"},
    {"var": "L_SE", "category": "Connectors & Agents", "name": "Wiz Runtime Sensors", "slide": "3, 4", "desc": "Active Wiz Runtime Sensor instances", "default": "0"},
    {"var": "CON_WOS", "category": "Connectors & Agents", "name": "Wiz Sensor Workloads", "slide": "3", "desc": "Workloads with Wiz Runtime Sensor installed", "default": "0"},
    {"var": "CON_K8S", "category": "Connectors & Agents", "name": "Kubernetes Connectors Count", "slide": "3", "desc": "Installed K8s connectors", "default": "0"},
    {"var": "CON_VCS", "category": "Connectors & Agents", "name": "VCS Connectors Count", "slide": "3", "desc": "GitHub, GitLab, Bitbucket connectors", "default": "0"},
    {"var": "CON_R", "category": "Connectors & Agents", "name": "Registry Connectors Count", "slide": "3", "desc": "Active container registry connectors", "default": "0"},
    {"var": "AE_TOT", "category": "Attack Surface Management", "name": "ASM Estimated Workloads", "slide": "11", "desc": "Calculated ASM compute workload units", "default": "0"},

    # --- System Health & Scans Snapshot (Slide 5) ---
    {"var": "SHI_C", "category": "System Health", "name": "Open Critical SHIs", "slide": "5", "desc": "Open Critical System Health Issues", "default": "0"},
    {"var": "SHI_H", "category": "System Health", "name": "Open High SHIs", "slide": "5", "desc": "Open High System Health Issues", "default": "0"},
    {"var": "SHI_R_C", "category": "System Health", "name": "Resolved Critical SHIs (30d)", "slide": "5", "desc": "Resolved Critical SHIs in past 30 days", "default": "0"},
    {"var": "SHI_R_H", "category": "System Health", "name": "Resolved High SHIs (30d)", "slide": "5", "desc": "Resolved High SHIs in past 30 days", "default": "0"},
    {"var": "SHI_O", "category": "System Health Breakdown", "name": "SHI - Outposts & Outpost Clusters", "slide": "5", "desc": "Open Crit+High SHIs on Outposts", "default": "0"},
    {"var": "SHI_CC", "category": "System Health Breakdown", "name": "SHI - Cloud Connectors", "slide": "5", "desc": "Open Crit+High SHIs on Cloud Connectors", "default": "0"},
    {"var": "SHI_I", "category": "System Health Breakdown", "name": "SHI - Integrations & Service Accounts", "slide": "5", "desc": "Open Crit+High SHIs on Integrations", "default": "0"},
    {"var": "SHI_RC", "category": "System Health Breakdown", "name": "SHI - Registry Connectors", "slide": "5", "desc": "Open Crit+High SHIs on Container Registries", "default": "0"},
    {"var": "SHI_KC", "category": "System Health Breakdown", "name": "SHI - Kubernetes Connectors", "slide": "5", "desc": "Open Crit+High SHIs on K8s Connectors", "default": "0"},
    {"var": "SHI_VCS", "category": "System Health Breakdown", "name": "SHI - VCS & CI/CD Connectors", "slide": "5", "desc": "Open Crit+High SHIs on Version Control", "default": "0"},
    {"var": "SHI_B", "category": "System Health Breakdown", "name": "SHI - Brokers & CLI", "slide": "5", "desc": "Open Crit+High SHIs on Brokers / CLI", "default": "0"},
    {"var": "NON_T", "category": "Non-OS Disk Scans", "name": "Non-OS Disk Total Scans", "slide": "5", "desc": "Total Non-OS disk scans evaluated", "default": "0"},
    {"var": "NON_F", "category": "Non-OS Disk Scans", "name": "Non-OS Disk Failed Scans", "slide": "5", "desc": "Failed Non-OS disk scans", "default": "0"},
    {"var": "NON_S", "category": "Non-OS Disk Scans", "name": "Non-OS Disk Skipped Scans", "slide": "5", "desc": "Skipped Non-OS disk scans", "default": "0"},
    {"var": "NON_C", "category": "Non-OS Disk Scans", "name": "Non-OS Disk Scan Coverage %", "slide": "5", "desc": "Coverage percentage (e.g. 35%)", "default": "0%"},
    {"var": "RCI_T", "category": "Container Image Scans", "name": "Container Image Total Scans", "slide": "5", "desc": "Total registry container image workload scans", "default": "0"},
    {"var": "RCI_F", "category": "Container Image Scans", "name": "Container Image Failed Scans", "slide": "5", "desc": "Failed container image scans", "default": "0"},
    {"var": "RCI_S", "category": "Container Image Scans", "name": "Container Image Skipped Scans", "slide": "5", "desc": "Skipped container image scans", "default": "0"},
    {"var": "RCI_C", "category": "Container Image Scans", "name": "Container Image Scan Coverage %", "slide": "5", "desc": "Coverage percentage (e.g. 16%)", "default": "0%"},
    {"var": "VMI_T", "category": "VM Image Scans", "name": "VM Image Total Scans", "slide": "5", "desc": "Total VM image workload scans", "default": "0"},
    {"var": "VMI_F", "category": "VM Image Scans", "name": "VM Image Failed Scans", "slide": "5", "desc": "Failed VM image scans", "default": "0"},
    {"var": "VMI_S", "category": "VM Image Scans", "name": "VM Image Skipped Scans", "slide": "5", "desc": "Skipped VM image scans", "default": "0"},
    {"var": "VMI_C", "category": "VM Image Scans", "name": "VM Image Scan Coverage %", "slide": "5", "desc": "Coverage percentage (e.g. 0%)", "default": "0%"},
    {"var": "DS_T", "category": "Data Security (DSPM) Scans", "name": "DSPM Total Scans", "slide": "5", "desc": "Total DSPM data security scans", "default": "0"},
    {"var": "DS_F", "category": "Data Security (DSPM) Scans", "name": "DSPM Failed Scans", "slide": "5", "desc": "Failed DSPM scans", "default": "0"},
    {"var": "DS_SK", "category": "Data Security (DSPM) Scans", "name": "DSPM Skipped Scans", "slide": "5", "desc": "Skipped DSPM scans", "default": "0"},
    {"var": "DS_P", "category": "Data Security (DSPM) Scans", "name": "DSPM Scan Coverage %", "slide": "5", "desc": "DSPM coverage percentage (e.g. 81%)", "default": "0%"},
    {"var": "DS_B", "category": "DSPM Breakdown", "name": "Storage Buckets Scanned", "slide": "5", "desc": "S3, GCS, Azure Blob buckets", "default": "0"},
    {"var": "DS_PD", "category": "DSPM Breakdown", "name": "PaaS Databases Scanned", "slide": "5", "desc": "RDS, Cloud SQL, CosmosDB", "default": "0"},
    {"var": "DS_DW", "category": "DSPM Breakdown", "name": "Data Warehouses Scanned", "slide": "5", "desc": "Snowflake, BigQuery, Redshift", "default": "0"},
    {"var": "DS_VD", "category": "DSPM Breakdown", "name": "Virtual Drives Scanned", "slide": "5", "desc": "EBS, Google Persistent Disks", "default": "0"},
    {"var": "DS_AI", "category": "DSPM Breakdown", "name": "AI Datastores Scanned", "slide": "5", "desc": "AI datasets / Knowledge bases", "default": "0"},
    {"var": "DS_FSS", "category": "DSPM Breakdown", "name": "File System Services Scanned", "slide": "5", "desc": "EFS, Azure Files, NetApp", "default": "0"},

    # --- Kubernetes Posture (Slide 6) ---
    {"var": "KC_C_T", "category": "Kubernetes", "name": "Total K8s Clusters", "slide": "6", "desc": "Total managed & self-hosted K8s clusters", "default": "0"},
    {"var": "KC_C_C", "category": "Kubernetes", "name": "Total K8s Containers", "slide": "6", "desc": "Total running container instances", "default": "0"},
    {"var": "KC_WC", "category": "Kubernetes", "name": "Clusters with Connector Deployed", "slide": "6", "desc": "Clusters with active Wiz K8s connector", "default": "0"},
    {"var": "KC_WA", "category": "Kubernetes", "name": "Clusters with Audit Log Ingestion", "slide": "6", "desc": "Clusters collecting K8s audit logs", "default": "0"},
    {"var": "KC_WS", "category": "Kubernetes", "name": "Clusters with Runtime Sensor", "slide": "6", "desc": "Clusters with Wiz Runtime Sensor daemonset", "default": "0"},
    {"var": "KC_AC", "category": "Kubernetes", "name": "Clusters with Admission Controller", "slide": "6", "desc": "Clusters with admission controller webhook", "default": "0"},
    {"var": "KG_NC", "category": "Kubernetes Gaps", "name": "Clusters Missing Connector", "slide": "6", "desc": "Unmanaged / unmonitored clusters", "default": "0"},
    {"var": "KG_NA", "category": "Kubernetes Gaps", "name": "Clusters Missing Audit Log Ingestion", "slide": "6", "desc": "Missing audit log ingestion", "default": "0"},
    {"var": "KG_NS", "category": "Kubernetes Gaps", "name": "Clusters Missing Runtime Sensor", "slide": "6", "desc": "Missing runtime threat detection", "default": "0"},
    {"var": "KG_AC", "category": "Kubernetes Gaps", "name": "Clusters Missing Admission Controller", "slide": "6", "desc": "Missing admission control enforcement", "default": "0"},

    # --- Top Controls by Issue Count (Slide 11) ---
    {"var": "CI_CONTROL_1", "category": "Top Controls", "name": "Top Critical Control 1 Name", "slide": "11", "desc": "Control with most critical issues", "default": ""},
    {"var": "CI_CBC_1", "category": "Top Controls", "name": "Top Critical Control 1 Count", "slide": "11", "desc": "Issue count for top critical control 1", "default": "0"},
    {"var": "CI_CONTROL_2", "category": "Top Controls", "name": "Top Critical Control 2 Name", "slide": "11", "desc": "Control with second most critical issues", "default": ""},
    {"var": "CI_CBC_2", "category": "Top Controls", "name": "Top Critical Control 2 Count", "slide": "11", "desc": "Issue count for top critical control 2", "default": "0"},
    {"var": "CI_CONTROL_3", "category": "Top Controls", "name": "Top Critical Control 3 Name", "slide": "11", "desc": "Control with third most critical issues", "default": ""},
    {"var": "CI_CBC_3", "category": "Top Controls", "name": "Top Critical Control 3 Count", "slide": "11", "desc": "Issue count for top critical control 3", "default": "0"},
    {"var": "HI_CONTROL_1", "category": "Top Controls", "name": "Top High Control 1 Name", "slide": "11", "desc": "Control with most high issues", "default": ""},
    {"var": "HI_CBC_1", "category": "Top Controls", "name": "Top High Control 1 Count", "slide": "11", "desc": "Issue count for top high control 1", "default": "0"},
    {"var": "HI_CONTROL_2", "category": "Top Controls", "name": "Top High Control 2 Name", "slide": "11", "desc": "Control with second most high issues", "default": ""},
    {"var": "HI_CBC_2", "category": "Top Controls", "name": "Top High Control 2 Count", "slide": "11", "desc": "Issue count for top high control 2", "default": "0"},
    {"var": "HI_CONTROL_3", "category": "Top Controls", "name": "Top High Control 3 Name", "slide": "11", "desc": "Control with third most high issues", "default": ""},
    {"var": "HI_CBC_3", "category": "Top Controls", "name": "Top High Control 3 Count", "slide": "11", "desc": "Issue count for top high control 3", "default": "0"},

    # --- Cloud Security Posture Snapshot (Slide 12) ---
    {"var": "SS", "category": "Security Posture", "name": "Current Security Score", "slide": "12", "desc": "Wiz Security Score (0-100%)", "default": "100"},
    {"var": "s1d", "category": "Security Posture", "name": "90-Day Security Score Trend", "slide": "12", "desc": "Score change (+/- %)", "default": "+0%"},
    {"var": "SP", "category": "Security Posture", "name": "Industry Benchmark Score", "slide": "12", "desc": "Peer benchmark security score (%)", "default": "80%"},
    {"var": "SG", "category": "Security Posture", "name": "Security Score Gap", "slide": "12", "desc": "Gap between current score and benchmark (%)", "default": "0%"},
    {"var": "SS_I", "category": "Security Posture", "name": "Industry Benchmark Name", "slide": "12", "desc": "e.g. Technology, Financial Services, Healthcare", "default": "Technology"},
    {"var": "OC", "category": "Security Posture", "name": "Open Critical Issues", "slide": "12", "desc": "Total active critical severity issues", "default": "0"},
    {"var": "RC", "category": "Security Posture", "name": "Resolved Critical Issues (90d)", "slide": "12", "desc": "Resolved critical issues in past 90 days", "default": "0"},
    {"var": "OH", "category": "Security Posture", "name": "Open High Issues", "slide": "12", "desc": "Total active high severity issues", "default": "0"},
    {"var": "RH", "category": "Security Posture", "name": "Resolved High Issues (90d)", "slide": "12", "desc": "Resolved high issues in past 90 days", "default": "0"},
    {"var": "RJ", "category": "Security Posture", "name": "Ignored Issues Count", "slide": "12", "desc": "Total issues in rejected / ignored status", "default": "0"},
    {"var": "OT", "category": "Threats & Runtime", "name": "Open Threats Count", "slide": "12", "desc": "Open runtime threat detections", "default": "0"},
    {"var": "RT", "category": "Threats & Runtime", "name": "Resolved Threats Count (90d)", "slide": "12", "desc": "Resolved threats in past 90 days", "default": "0"},
    {"var": "MTTR_O", "category": "Threats & Runtime", "name": "Mean Time to Remediate (MTTR)", "slide": "12", "desc": "Average MTTR in days for criticals/threats", "default": "0"},
    {"var": "AVG_AGEC", "category": "Threats & Runtime", "name": "Critical Issues Average Age", "slide": "12", "desc": "Average age of open critical issues (days)", "default": "0"},
    {"var": "AVG_AGEH", "category": "Threats & Runtime", "name": "High Issues Average Age", "slide": "12", "desc": "Average age of open high issues (days)", "default": "0"},
    {"var": "AI_SF", "category": "AI Security Findings", "name": "AI Security Findings Count", "slide": "12", "desc": "Active AI security posture findings", "default": "0"},
    {"var": "AI_MF", "category": "AI Security Findings", "name": "AI Misconfiguration Findings Count", "slide": "12", "desc": "Configuration findings for AI framework (wct-id-1998)", "default": "0"},
    {"var": "AI_IF", "category": "AI Security Findings", "name": "AI Inventory Findings Count", "slide": "12", "desc": "Inventory findings for AI models & MCP servers", "default": "0"},

    # --- Licenses & Add-ons (Slide 14) ---
    {"var": "L_CW", "category": "Licenses", "name": "Cloud Workload Protection License", "slide": "14", "desc": "Active / Billable unit count", "default": "Active"},
    {"var": "L_CO", "category": "Licenses", "name": "Wiz Code License", "slide": "14", "desc": "Active / Inactive", "default": "Active"},
    {"var": "L_DE", "category": "Licenses", "name": "Wiz Defend License", "slide": "14", "desc": "Active / Inactive", "default": "Active"},
    {"var": "L_CL_PCT", "category": "Licenses", "name": "Container Lifecycle Coverage %", "slide": "14", "desc": "Container lifecycle scanning coverage", "default": "100%"},

    # --- Potential Integrations (Slide 15) ---
    {"var": "PI_T1_N", "category": "Potential Integrations", "name": "Top Integration 1 Name", "slide": "15", "desc": "Most active cloud service technology", "default": "AWS IAM"},
    {"var": "PI_T1_D", "category": "Potential Integrations", "name": "Top Integration 1 Timeline Date", "slide": "15", "desc": "Last activity date (YYYY-MM-DD)", "default": ""},
    {"var": "PI_T1_NT", "category": "Potential Integrations", "name": "Top Integration 1 Total Instances", "slide": "15", "desc": "Total discovered service accounts", "default": "0"},
    {"var": "PI_T1_NS", "category": "Potential Integrations", "name": "Top Integration 1 External Owners", "slide": "15", "desc": "Accounts with external owners", "default": "0"},
    {"var": "PI_T2_N", "category": "Potential Integrations", "name": "Top Integration 2 Name", "slide": "15", "desc": "Second most active technology", "default": ""},
    {"var": "PI_T2_D", "category": "Potential Integrations", "name": "Top Integration 2 Timeline Date", "slide": "15", "desc": "Last activity date", "default": ""},
    {"var": "PI_T2_NT", "category": "Potential Integrations", "name": "Top Integration 2 Total Instances", "slide": "15", "desc": "Total discovered instances", "default": "0"},
    {"var": "PI_T2_NS", "category": "Potential Integrations", "name": "Top Integration 2 External Owners", "slide": "15", "desc": "Accounts with external owners", "default": "0"},
    {"var": "PI_T3_N", "category": "Potential Integrations", "name": "Top Integration 3 Name", "slide": "15", "desc": "Third most active technology", "default": ""},
    {"var": "PI_T3_D", "category": "Potential Integrations", "name": "Top Integration 3 Timeline Date", "slide": "15", "desc": "Last activity date", "default": ""},
    {"var": "PI_T3_NT", "category": "Potential Integrations", "name": "Top Integration 3 Total Instances", "slide": "15", "desc": "Total discovered instances", "default": "0"},
    {"var": "PI_T3_NS", "category": "Potential Integrations", "name": "Top Integration 3 External Owners", "slide": "15", "desc": "Accounts with external owners", "default": "0"},

    # --- Auto-generated: full coverage of remaining template {{ }} tokens (2026-09-01) ---
    # Titles/descriptions grounded in template slide labels + processor computation.
    {"var": "AE_HTTP", "category": "Metrics", "name": "HTTP/HTTPS App Endpoints", "slide": "13", "desc": "Application endpoints on HTTP/HTTPS protocols", "default": ""},
    {"var": "AE_NHTTP", "category": "Metrics", "name": "Non-HTTP App Endpoints", "slide": "13", "desc": "Application endpoints on non-HTTP protocols", "default": ""},
    {"var": "ALL_NON_BILLABLE_PREVIEW", "category": "Preview Hub", "name": "All Non-Billable Public Previews", "slide": "7", "desc": "Bullet list of all non-billable public-preview features enabled", "default": ""},
    {"var": "ASM_API", "category": "Attack Surface Management", "name": "Advanced Scan Source: API Security", "slide": "17", "desc": "ASM setting: Advanced Scan Source: API Security", "default": ""},
    {"var": "ASM_API_R", "category": "Attack Surface Management", "name": "Advanced Scan Source: API Security - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Advanced Scan Source: API Security", "default": ""},
    {"var": "ASM_CODE", "category": "Attack Surface Management", "name": "Advanced Scan Source: Code", "slide": "17", "desc": "ASM setting: Advanced Scan Source: Code", "default": ""},
    {"var": "ASM_CODE_R", "category": "Attack Surface Management", "name": "Advanced Scan Source: Code - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Advanced Scan Source: Code", "default": ""},
    {"var": "ASM_CRED", "category": "Attack Surface Management", "name": "Rules: Default Credentials Detection", "slide": "17", "desc": "ASM setting: Rules: Default Credentials Detection", "default": ""},
    {"var": "ASM_CRED_R", "category": "Attack Surface Management", "name": "Rules: Default Credentials Detection - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Rules: Default Credentials Detection", "default": ""},
    {"var": "ASM_CUST", "category": "Attack Surface Management", "name": "Advanced Scan Source: Custom Targets", "slide": "17", "desc": "ASM setting: Advanced Scan Source: Custom Targets", "default": ""},
    {"var": "ASM_CUST_R", "category": "Attack Surface Management", "name": "Advanced Scan Source: Custom Targets - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Advanced Scan Source: Custom Targets", "default": ""},
    {"var": "ASM_DAST", "category": "Attack Surface Management", "name": "Rules: DAST", "slide": "17", "desc": "ASM setting: Rules: DAST", "default": ""},
    {"var": "ASM_DAST_R", "category": "Attack Surface Management", "name": "Rules: DAST - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Rules: DAST", "default": ""},
    {"var": "ASM_DATA", "category": "Attack Surface Management", "name": "Risk: Sensitive Data Findings Detection", "slide": "17", "desc": "ASM setting: Risk: Sensitive Data Findings Detection", "default": ""},
    {"var": "ASM_DATA_R", "category": "Attack Surface Management", "name": "Risk: Sensitive Data Findings Detection - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Risk: Sensitive Data Findings Detection", "default": ""},
    {"var": "ASM_EAR", "category": "Attack Surface Management", "name": "Rules: Early Access Rules", "slide": "17", "desc": "ASM setting: Rules: Early Access Rules", "default": ""},
    {"var": "ASM_EAR_R", "category": "Attack Surface Management", "name": "Rules: Early Access Rules - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Rules: Early Access Rules", "default": ""},
    {"var": "ASM_EXPL", "category": "Attack Surface Management", "name": "Application Endpoint Exposure Level", "slide": "17", "desc": "ASM setting: Application Endpoint Exposure Level", "default": ""},
    {"var": "ASM_EXPL_R", "category": "Attack Surface Management", "name": "Application Endpoint Exposure Level - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Application Endpoint Exposure Level", "default": ""},
    {"var": "ASM_HPT", "category": "Attack Surface Management", "name": "Rules: High-Profile Threat Detection", "slide": "17", "desc": "ASM setting: Rules: High-Profile Threat Detection", "default": ""},
    {"var": "ASM_HPT_R", "category": "Attack Surface Management", "name": "Rules: High-Profile Threat Detection - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Rules: High-Profile Threat Detection", "default": ""},
    {"var": "ASM_MISC", "category": "Attack Surface Management", "name": "Rules: Misconfiguration Detection", "slide": "17", "desc": "ASM setting: Rules: Misconfiguration Detection", "default": ""},
    {"var": "ASM_MISC_R", "category": "Attack Surface Management", "name": "Rules: Misconfiguration Detection - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Rules: Misconfiguration Detection", "default": ""},
    {"var": "ASM_MODE", "category": "Attack Surface Management", "name": "Scanner Mode (Basic/Advanced)", "slide": "17", "desc": "ASM setting: Scanner Mode (Basic/Advanced)", "default": ""},
    {"var": "ASM_MODE_R", "category": "Attack Surface Management", "name": "Scanner Mode (Basic/Advanced) - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Scanner Mode (Basic/Advanced)", "default": ""},
    {"var": "ASM_RECON", "category": "Attack Surface Management", "name": "Advanced Scan Source: Reconnaissance", "slide": "17", "desc": "ASM setting: Advanced Scan Source: Reconnaissance", "default": ""},
    {"var": "ASM_RECON_R", "category": "Attack Surface Management", "name": "Advanced Scan Source: Reconnaissance - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Advanced Scan Source: Reconnaissance", "default": ""},
    {"var": "ASM_RS", "category": "Attack Surface Management", "name": "Advanced Scan Source: Runtime Sensor", "slide": "17", "desc": "ASM setting: Advanced Scan Source: Runtime Sensor", "default": ""},
    {"var": "ASM_RS_R", "category": "Attack Surface Management", "name": "Advanced Scan Source: Runtime Sensor - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Advanced Scan Source: Runtime Sensor", "default": ""},
    {"var": "ASM_SAAS", "category": "Attack Surface Management", "name": "Advanced Scan Source: SaaS", "slide": "17", "desc": "ASM setting: Advanced Scan Source: SaaS", "default": ""},
    {"var": "ASM_SASS_R", "category": "Attack Surface Management", "name": "Advanced Scan Source: SaaS - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Advanced Scan Source: SaaS", "default": ""},
    {"var": "ASM_SEC", "category": "Attack Surface Management", "name": "Risk: Secret Findings Detection", "slide": "17", "desc": "ASM setting: Risk: Secret Findings Detection", "default": ""},
    {"var": "ASM_SEC_R", "category": "Attack Surface Management", "name": "Risk: Secret Findings Detection - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Risk: Secret Findings Detection", "default": ""},
    {"var": "ASM_SV", "category": "Attack Surface Management", "name": "Risk: Secret Validation", "slide": "17", "desc": "ASM setting: Risk: Secret Validation", "default": ""},
    {"var": "ASM_SV_R", "category": "Attack Surface Management", "name": "Risk: Secret Validation - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Risk: Secret Validation", "default": ""},
    {"var": "ASM_VEXP", "category": "Attack Surface Management", "name": "Rules: Vulnerability Exploitability", "slide": "17", "desc": "ASM setting: Rules: Vulnerability Exploitability", "default": ""},
    {"var": "ASM_VEXP_R", "category": "Attack Surface Management", "name": "Rules: Vulnerability Exploitability - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Rules: Vulnerability Exploitability", "default": ""},
    {"var": "ASM_VULN", "category": "Attack Surface Management", "name": "Risk: Vulnerability Assessment", "slide": "17", "desc": "ASM setting: Risk: Vulnerability Assessment", "default": ""},
    {"var": "ASM_VULN_R", "category": "Attack Surface Management", "name": "Risk: Vulnerability Assessment - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Risk: Vulnerability Assessment", "default": ""},
    {"var": "BILLABLE_ADVANCED", "category": "Preview Hub", "name": "Billable Public Previews - Advanced", "slide": "7", "desc": "Billable public-preview features enabled under the Advanced tier", "default": ""},
    {"var": "BILLABLE_CODE", "category": "Preview Hub", "name": "Billable Public Previews - Code", "slide": "7", "desc": "Billable public-preview features enabled under the Code tier", "default": ""},
    {"var": "BILLABLE_DEFEND", "category": "Preview Hub", "name": "Billable Public Previews - Defend", "slide": "7", "desc": "Billable public-preview features enabled under the Defend tier", "default": ""},
    {"var": "BILLABLE_SENSOR", "category": "Preview Hub", "name": "Billable Public Previews - Sensor", "slide": "7", "desc": "Billable public-preview features enabled under the Sensor tier", "default": ""},
    {"var": "CC_TOT", "category": "Metrics", "name": "Champion Center Items", "slide": "6", "desc": "Total Champion Center journey items for the tenant", "default": ""},
    {"var": "CE_1", "category": "Cloud Events", "name": "Cloud Event Count #1", "slide": "3", "desc": "Matched event count for the #1 cloud-event origin", "default": ""},
    {"var": "CE_10", "category": "Cloud Events", "name": "Cloud Event Count #10", "slide": "3", "desc": "Matched event count for the #10 cloud-event origin", "default": ""},
    {"var": "CE_11", "category": "Cloud Events", "name": "Cloud Event Count #11", "slide": "3", "desc": "Matched event count for the #11 cloud-event origin", "default": ""},
    {"var": "CE_12", "category": "Cloud Events", "name": "Cloud Event Count #12", "slide": "3", "desc": "Matched event count for the #12 cloud-event origin", "default": ""},
    {"var": "CE_13", "category": "Cloud Events", "name": "Cloud Event Count #13", "slide": "3", "desc": "Matched event count for the #13 cloud-event origin", "default": ""},
    {"var": "CE_2", "category": "Cloud Events", "name": "Cloud Event Count #2", "slide": "3", "desc": "Matched event count for the #2 cloud-event origin", "default": ""},
    {"var": "CE_3", "category": "Cloud Events", "name": "Cloud Event Count #3", "slide": "3", "desc": "Matched event count for the #3 cloud-event origin", "default": ""},
    {"var": "CE_4", "category": "Cloud Events", "name": "Cloud Event Count #4", "slide": "3", "desc": "Matched event count for the #4 cloud-event origin", "default": ""},
    {"var": "CE_5", "category": "Cloud Events", "name": "Cloud Event Count #5", "slide": "3", "desc": "Matched event count for the #5 cloud-event origin", "default": ""},
    {"var": "CE_6", "category": "Cloud Events", "name": "Cloud Event Count #6", "slide": "3", "desc": "Matched event count for the #6 cloud-event origin", "default": ""},
    {"var": "CE_7", "category": "Cloud Events", "name": "Cloud Event Count #7", "slide": "3", "desc": "Matched event count for the #7 cloud-event origin", "default": ""},
    {"var": "CE_8", "category": "Cloud Events", "name": "Cloud Event Count #8", "slide": "3", "desc": "Matched event count for the #8 cloud-event origin", "default": ""},
    {"var": "CE_9", "category": "Cloud Events", "name": "Cloud Event Count #9", "slide": "3", "desc": "Matched event count for the #9 cloud-event origin", "default": ""},
    {"var": "CLI", "category": "Metrics", "name": "Wiz CLI Scans (30d)", "slide": "4", "desc": "CI/CD (Wiz CLI) scans in the last 30 days", "default": ""},
    {"var": "CLOUD_EVENTS_1", "category": "Cloud Events", "name": "Cloud Event Origin #1", "slide": "3", "desc": "Display name of the #1 cloud-event origin by volume", "default": ""},
    {"var": "CLOUD_EVENTS_10", "category": "Cloud Events", "name": "Cloud Event Origin #10", "slide": "3", "desc": "Display name of the #10 cloud-event origin by volume", "default": ""},
    {"var": "CLOUD_EVENTS_11", "category": "Cloud Events", "name": "Cloud Event Origin #11", "slide": "3", "desc": "Display name of the #11 cloud-event origin by volume", "default": ""},
    {"var": "CLOUD_EVENTS_12", "category": "Cloud Events", "name": "Cloud Event Origin #12", "slide": "3", "desc": "Display name of the #12 cloud-event origin by volume", "default": ""},
    {"var": "CLOUD_EVENTS_13", "category": "Cloud Events", "name": "Cloud Event Origin #13", "slide": "3", "desc": "Display name of the #13 cloud-event origin by volume", "default": ""},
    {"var": "CLOUD_EVENTS_2", "category": "Cloud Events", "name": "Cloud Event Origin #2", "slide": "3", "desc": "Display name of the #2 cloud-event origin by volume", "default": ""},
    {"var": "CLOUD_EVENTS_3", "category": "Cloud Events", "name": "Cloud Event Origin #3", "slide": "3", "desc": "Display name of the #3 cloud-event origin by volume", "default": ""},
    {"var": "CLOUD_EVENTS_4", "category": "Cloud Events", "name": "Cloud Event Origin #4", "slide": "3", "desc": "Display name of the #4 cloud-event origin by volume", "default": ""},
    {"var": "CLOUD_EVENTS_5", "category": "Cloud Events", "name": "Cloud Event Origin #5", "slide": "3", "desc": "Display name of the #5 cloud-event origin by volume", "default": ""},
    {"var": "CLOUD_EVENTS_6", "category": "Cloud Events", "name": "Cloud Event Origin #6", "slide": "3", "desc": "Display name of the #6 cloud-event origin by volume", "default": ""},
    {"var": "CLOUD_EVENTS_7", "category": "Cloud Events", "name": "Cloud Event Origin #7", "slide": "3", "desc": "Display name of the #7 cloud-event origin by volume", "default": ""},
    {"var": "CLOUD_EVENTS_8", "category": "Cloud Events", "name": "Cloud Event Origin #8", "slide": "3", "desc": "Display name of the #8 cloud-event origin by volume", "default": ""},
    {"var": "CLOUD_EVENTS_9", "category": "Cloud Events", "name": "Cloud Event Origin #9", "slide": "3", "desc": "Display name of the #9 cloud-event origin by volume", "default": ""},
    {"var": "CL_ASMP", "category": "Metrics", "name": "Cloud Advanced - Advanced ASM %", "slide": "4", "desc": "Advanced ASM enabled (100) or not (0)", "default": ""},
    {"var": "CL_BLD", "category": "Metrics", "name": "Container Images - Build Stage", "slide": "15", "desc": "Container images detected at the Build lifecycle stage", "default": ""},
    {"var": "CL_CLD", "category": "Metrics", "name": "Container Images - Cloud Stage", "slide": "15", "desc": "Container images detected at the Cloud (running) lifecycle stage", "default": ""},
    {"var": "CL_CODE", "category": "Metrics", "name": "Container Images - Code Stage", "slide": "15", "desc": "Container images detected at the Code lifecycle stage", "default": ""},
    {"var": "CL_CP", "category": "Metrics", "name": "Cloud Advanced - Compute %", "slide": "4", "desc": "Compute workload scanning coverage (slide-4 adoption)", "default": ""},
    {"var": "CL_DEP", "category": "Metrics", "name": "Container Images - Deploy Stage", "slide": "15", "desc": "Container images detected at the Deploy lifecycle stage", "default": ""},
    {"var": "CL_DP", "category": "Metrics", "name": "Cloud Advanced - Data %", "slide": "4", "desc": "DSPM data scanning coverage (slide-4 adoption)", "default": ""},
    {"var": "CL_NRVP", "category": "Metrics", "name": "Cloud Advanced - Non-OS/Registry/VM Image %", "slide": "4", "desc": "Combined non-OS/registry/VM image scan coverage", "default": ""},
    {"var": "CL_REDA", "category": "Metrics", "name": "Cloud Advanced - Red Agent %", "slide": "4", "desc": "Red Agent enabled (100) or not (0)", "default": ""},
    {"var": "CL_RT", "category": "Metrics", "name": "Container Images - Runtime Stage", "slide": "15", "desc": "Container images detected at the Runtime lifecycle stage", "default": ""},
    {"var": "CL_STR", "category": "Metrics", "name": "Container Images - Registry/Store Stage", "slide": "15", "desc": "Container images detected in registries (Store stage)", "default": ""},
    {"var": "CL_SUP", "category": "Metrics", "name": "Cloud Advanced - SaaS Users %", "slide": "4", "desc": "SaaS security scanner enabled (100) or not (0)", "default": ""},
    {"var": "CL_UVMP", "category": "Metrics", "name": "Cloud Advanced - Unified Vuln Mgmt %", "slide": "4", "desc": "Share of vulnerability-assessment detections enabled", "default": ""},
    {"var": "CL_WOP", "category": "Metrics", "name": "Cloud Advanced - WizOS %", "slide": "4", "desc": "WizOS workloads as a percent of compute workloads", "default": ""},
    {"var": "CONTRACT_END_FMT", "category": "Metrics", "name": "Contract End Date (formatted)", "slide": "4", "desc": "Current contract end date, MM/DD/YYYY", "default": ""},
    {"var": "CON_BRO", "category": "Metrics", "name": "Connectors - Errored", "slide": "3", "desc": "Connectors in an error/broken state", "default": ""},
    {"var": "CON_DIS", "category": "Metrics", "name": "Connectors - Disabled", "slide": "3", "desc": "Connectors currently disabled", "default": ""},
    {"var": "CON_EN", "category": "Metrics", "name": "Connectors - Connected", "slide": "3", "desc": "Connectors in a healthy connected state", "default": ""},
    {"var": "CON_NE", "category": "Metrics", "name": "Connectors - No Cloud Events", "slide": "3", "desc": "Connectors not ingesting cloud events", "default": ""},
    {"var": "CON_WE", "category": "Metrics", "name": "Connectors - With Cloud Events", "slide": "3", "desc": "Connectors ingesting cloud events", "default": ""},
    {"var": "CUS_NOD", "category": "Metrics", "name": "Days as Wiz Customer", "slide": "4", "desc": "Days since the tenant was created", "default": ""},
    {"var": "Customer", "category": "General", "name": "Customer Name (alt token)", "slide": "1", "desc": "Customer organization / tenant name", "default": ""},
    {"var": "DSS_AIAO", "category": "Data Security Scanner Config", "name": "Azure OpenAI", "slide": "18", "desc": "Data security scanner coverage: Azure OpenAI", "default": ""},
    {"var": "DSS_AIAO_R", "category": "Data Security Scanner Config", "name": "Azure OpenAI - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Azure OpenAI", "default": ""},
    {"var": "DSS_AIOA", "category": "Data Security Scanner Config", "name": "OpenAI", "slide": "18", "desc": "Data security scanner coverage: OpenAI", "default": ""},
    {"var": "DSS_AIOA_R", "category": "Data Security Scanner Config", "name": "OpenAI - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: OpenAI", "default": ""},
    {"var": "DSS_AIV", "category": "Data Security Scanner Config", "name": "Vertex AI", "slide": "18", "desc": "Data security scanner coverage: Vertex AI", "default": ""},
    {"var": "DSS_AIV_R", "category": "Data Security Scanner Config", "name": "Vertex AI - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Vertex AI", "default": ""},
    {"var": "DSS_AZ1", "category": "Data Security Scanner Config", "name": "Storage: Azure Private Endpoints (Disabled Public)", "slide": "18", "desc": "Data security scanner coverage: Storage: Azure Private Endpoints (Disabled Public)", "default": ""},
    {"var": "DSS_AZ1_R", "category": "Data Security Scanner Config", "name": "Storage: Azure Private Endpoints (Disabled Public) - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Storage: Azure Private Endpoints (Disabled Public)", "default": ""},
    {"var": "DSS_AZ2", "category": "Data Security Scanner Config", "name": "Storage: Azure Private Endpoints (Selected VNets)", "slide": "18", "desc": "Data security scanner coverage: Storage: Azure Private Endpoints (Selected VNets)", "default": ""},
    {"var": "DSS_AZ2_R", "category": "Data Security Scanner Config", "name": "Storage: Azure Private Endpoints (Selected VNets) - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Storage: Azure Private Endpoints (Selected VNets)", "default": ""},
    {"var": "DSS_BQ", "category": "Data Security Scanner Config", "name": "Google BigQuery", "slide": "18", "desc": "Data security scanner coverage: Google BigQuery", "default": ""},
    {"var": "DSS_BQ_R", "category": "Data Security Scanner Config", "name": "Google BigQuery - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Google BigQuery", "default": ""},
    {"var": "DSS_BUCK", "category": "Data Security Scanner Config", "name": "Buckets (Public & Private)", "slide": "18", "desc": "Data security scanner coverage: Buckets (Public & Private)", "default": ""},
    {"var": "DSS_BUCK_R", "category": "Data Security Scanner Config", "name": "Buckets (Public & Private) - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Buckets (Public & Private)", "default": ""},
    {"var": "DSS_CDBAZ1", "category": "Data Security Scanner Config", "name": "CosmosDB: Azure Private Endpoints (Disabled Public)", "slide": "18", "desc": "Data security scanner coverage: CosmosDB: Azure Private Endpoints (Disabled Public)", "default": ""},
    {"var": "DSS_CDBAZ1_R", "category": "Data Security Scanner Config", "name": "CosmosDB: Azure Private Endpoints (Disabled Public) - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: CosmosDB: Azure Private Endpoints (Disabled Public)", "default": ""},
    {"var": "DSS_CDBAZ2", "category": "Data Security Scanner Config", "name": "CosmosDB: Azure Private Endpoints (Selected VNets)", "slide": "18", "desc": "Data security scanner coverage: CosmosDB: Azure Private Endpoints (Selected VNets)", "default": ""},
    {"var": "DSS_CDBAZ2_R", "category": "Data Security Scanner Config", "name": "CosmosDB: Azure Private Endpoints (Selected VNets) - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: CosmosDB: Azure Private Endpoints (Selected VNets)", "default": ""},
    {"var": "DSS_DDB", "category": "Data Security Scanner Config", "name": "Amazon DynamoDB", "slide": "18", "desc": "Data security scanner coverage: Amazon DynamoDB", "default": ""},
    {"var": "DSS_DDB_R", "category": "Data Security Scanner Config", "name": "Amazon DynamoDB - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Amazon DynamoDB", "default": ""},
    {"var": "DSS_DW", "category": "Data Security Scanner Config", "name": "Data Warehouses", "slide": "18", "desc": "Data security scanner coverage: Data Warehouses", "default": ""},
    {"var": "DSS_DW_R", "category": "Data Security Scanner Config", "name": "Data Warehouses - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Data Warehouses", "default": ""},
    {"var": "DSS_IAAS", "category": "Data Security Scanner Config", "name": "Hosted Databases (IaaS)", "slide": "18", "desc": "Data security scanner coverage: Hosted Databases (IaaS)", "default": ""},
    {"var": "DSS_IAAS_R", "category": "Data Security Scanner Config", "name": "Hosted Databases (IaaS) - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Hosted Databases (IaaS)", "default": ""},
    {"var": "DSS_ON", "category": "Data Security Scanner Config", "name": "Data Security Scanner (master toggle)", "slide": "18", "desc": "Data security scanner coverage: Data Security Scanner (master toggle)", "default": ""},
    {"var": "DSS_ON_R", "category": "Data Security Scanner Config", "name": "Data Security Scanner (master toggle) - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Data Security Scanner (master toggle)", "default": ""},
    {"var": "DSS_PAAS", "category": "Data Security Scanner Config", "name": "Cloud Managed Databases (PaaS)", "slide": "18", "desc": "Data security scanner coverage: Cloud Managed Databases (PaaS)", "default": ""},
    {"var": "DSS_PAAS_R", "category": "Data Security Scanner Config", "name": "Cloud Managed Databases (PaaS) - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Cloud Managed Databases (PaaS)", "default": ""},
    {"var": "DSS_SHAD", "category": "Data Security Scanner Config", "name": "Shadow Data", "slide": "18", "desc": "Data security scanner coverage: Shadow Data", "default": ""},
    {"var": "DSS_SHAD_R", "category": "Data Security Scanner Config", "name": "Shadow Data - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Shadow Data", "default": ""},
    {"var": "DSS_SLS", "category": "Data Security Scanner Config", "name": "Serverless Functions", "slide": "18", "desc": "Data security scanner coverage: Serverless Functions", "default": ""},
    {"var": "DSS_SLS_R", "category": "Data Security Scanner Config", "name": "Serverless Functions - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Serverless Functions", "default": ""},
    {"var": "DSS_SNOW", "category": "Data Security Scanner Config", "name": "Snowflake", "slide": "18", "desc": "Data security scanner coverage: Snowflake", "default": ""},
    {"var": "DSS_SNOW_R", "category": "Data Security Scanner Config", "name": "Snowflake - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Snowflake", "default": ""},
    {"var": "DSS_VDRV", "category": "Data Security Scanner Config", "name": "Virtual Drives", "slide": "18", "desc": "Data security scanner coverage: Virtual Drives", "default": ""},
    {"var": "DSS_VDRV_R", "category": "Data Security Scanner Config", "name": "Virtual Drives - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Virtual Drives", "default": ""},
    {"var": "DSS_VMD", "category": "Data Security Scanner Config", "name": "VM Disks (OS and non-OS)", "slide": "18", "desc": "Data security scanner coverage: VM Disks (OS and non-OS)", "default": ""},
    {"var": "DSS_VMD_R", "category": "Data Security Scanner Config", "name": "VM Disks (OS and non-OS) - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: VM Disks (OS and non-OS)", "default": ""},
    {"var": "D_U_R", "category": "Metrics", "name": "Days Until Renewal", "slide": "4", "desc": "Days remaining until contract renewal", "default": ""},
    {"var": "F_AR", "category": "Adoption & Governance", "name": "Automation Rules (On / Off)", "slide": "6", "desc": "Automation rules enabled vs disabled", "default": ""},
    {"var": "F_BA", "category": "Adoption & Governance", "name": "Blue Agent Enabled", "slide": "6, 13", "desc": "Whether the Wiz Blue Agent is enabled", "default": ""},
    {"var": "F_BE", "category": "Adoption & Governance", "name": "Using Wiz Browser Extension", "slide": "6", "desc": "Distinct users of the Wiz AI browser extension", "default": ""},
    {"var": "F_DR", "category": "Adoption & Governance", "name": "Service Catalog Discovery Rules", "slide": "6", "desc": "Application/service discovery rules configured", "default": ""},
    {"var": "F_FW", "category": "Adoption & Governance", "name": "Custom Compliance Frameworks", "slide": "6", "desc": "Count of user-created custom compliance frameworks enabled", "default": ""},
    {"var": "F_GA", "category": "Adoption & Governance", "name": "Green Agent Enabled", "slide": "6, 13", "desc": "Whether the Wiz Green Agent (WizOS) is enabled", "default": ""},
    {"var": "F_IR", "category": "Adoption & Governance", "name": "Inventory Management Rules", "slide": "6", "desc": "Total inventory management rules configured", "default": ""},
    {"var": "F_MM", "category": "Adoption & Governance", "name": "User Created Monitored Metrics", "slide": "6", "desc": "Custom monitored metrics created by the customer", "default": ""},
    {"var": "F_PP", "category": "Adoption & Governance", "name": "User Created Posture Policies", "slide": "6", "desc": "Custom posture policies created by the customer", "default": ""},
    {"var": "F_RA", "category": "Adoption & Governance", "name": "Red Agent Enabled", "slide": "6, 13", "desc": "Whether the Wiz Red Agent (offensive) is enabled", "default": ""},
    {"var": "F_TR", "category": "Adoption & Governance", "name": "Resource Tag Rules (On / Off)", "slide": "6", "desc": "Resource tagging rules enabled vs disabled", "default": ""},
    {"var": "F_WF", "category": "Adoption & Governance", "name": "Automation Workflows", "slide": "6", "desc": "Automation workflows enabled vs disabled", "default": ""},
    {"var": "F_WMCP", "category": "Adoption & Governance", "name": "Wiz MCP Users", "slide": "6", "desc": "Distinct users of the Wiz MCP integration", "default": ""},
    {"var": "IA_1", "category": "Integrations Activity", "name": "Integration #1 Name", "slide": "6", "desc": "Name of the #1 most-recently-active integration", "default": ""},
    {"var": "IA_10", "category": "Integrations Activity", "name": "Integration #10 Name", "slide": "6", "desc": "Name of the #10 most-recently-active integration", "default": ""},
    {"var": "IA_2", "category": "Integrations Activity", "name": "Integration #2 Name", "slide": "6", "desc": "Name of the #2 most-recently-active integration", "default": ""},
    {"var": "IA_3", "category": "Integrations Activity", "name": "Integration #3 Name", "slide": "6", "desc": "Name of the #3 most-recently-active integration", "default": ""},
    {"var": "IA_4", "category": "Integrations Activity", "name": "Integration #4 Name", "slide": "6", "desc": "Name of the #4 most-recently-active integration", "default": ""},
    {"var": "IA_5", "category": "Integrations Activity", "name": "Integration #5 Name", "slide": "6", "desc": "Name of the #5 most-recently-active integration", "default": ""},
    {"var": "IA_6", "category": "Integrations Activity", "name": "Integration #6 Name", "slide": "6", "desc": "Name of the #6 most-recently-active integration", "default": ""},
    {"var": "IA_7", "category": "Integrations Activity", "name": "Integration #7 Name", "slide": "6", "desc": "Name of the #7 most-recently-active integration", "default": ""},
    {"var": "IA_8", "category": "Integrations Activity", "name": "Integration #8 Name", "slide": "6", "desc": "Name of the #8 most-recently-active integration", "default": ""},
    {"var": "IA_9", "category": "Integrations Activity", "name": "Integration #9 Name", "slide": "6", "desc": "Name of the #9 most-recently-active integration", "default": ""},
    {"var": "IR_1", "category": "Integrations Activity", "name": "Integration #1 Last Activity", "slide": "6", "desc": "Last activity/tested date for integration #1", "default": ""},
    {"var": "IR_10", "category": "Integrations Activity", "name": "Integration #10 Last Activity", "slide": "6", "desc": "Last activity/tested date for integration #10", "default": ""},
    {"var": "IR_2", "category": "Integrations Activity", "name": "Integration #2 Last Activity", "slide": "6", "desc": "Last activity/tested date for integration #2", "default": ""},
    {"var": "IR_3", "category": "Integrations Activity", "name": "Integration #3 Last Activity", "slide": "6", "desc": "Last activity/tested date for integration #3", "default": ""},
    {"var": "IR_4", "category": "Integrations Activity", "name": "Integration #4 Last Activity", "slide": "6", "desc": "Last activity/tested date for integration #4", "default": ""},
    {"var": "IR_5", "category": "Integrations Activity", "name": "Integration #5 Last Activity", "slide": "6", "desc": "Last activity/tested date for integration #5", "default": ""},
    {"var": "IR_6", "category": "Integrations Activity", "name": "Integration #6 Last Activity", "slide": "6", "desc": "Last activity/tested date for integration #6", "default": ""},
    {"var": "IR_7", "category": "Integrations Activity", "name": "Integration #7 Last Activity", "slide": "6", "desc": "Last activity/tested date for integration #7", "default": ""},
    {"var": "IR_8", "category": "Integrations Activity", "name": "Integration #8 Last Activity", "slide": "6", "desc": "Last activity/tested date for integration #8", "default": ""},
    {"var": "IR_9", "category": "Integrations Activity", "name": "Integration #9 Last Activity", "slide": "6", "desc": "Last activity/tested date for integration #9", "default": ""},
    {"var": "K8C_1", "category": "Kubernetes", "name": "K8s Distribution #1 Count", "slide": "15", "desc": "Cluster count for the #1 Kubernetes distribution", "default": ""},
    {"var": "K8C_2", "category": "Kubernetes", "name": "K8s Distribution #2 Count", "slide": "15", "desc": "Cluster count for the #2 Kubernetes distribution", "default": ""},
    {"var": "K8C_3", "category": "Kubernetes", "name": "K8s Distribution #3 Count", "slide": "15", "desc": "Cluster count for the #3 Kubernetes distribution", "default": ""},
    {"var": "K8C_4", "category": "Kubernetes", "name": "K8s Distribution #4 Count", "slide": "15", "desc": "Cluster count for the #4 Kubernetes distribution", "default": ""},
    {"var": "K8C_5", "category": "Kubernetes", "name": "K8s Distribution #5 Count", "slide": "15", "desc": "Cluster count for the #5 Kubernetes distribution", "default": ""},
    {"var": "K8C_OTH", "category": "Metrics", "name": "K8s Clusters - Other Distributions", "slide": "15", "desc": "Cluster count outside the top 5 distributions", "default": ""},
    {"var": "K8C_TOT", "category": "Metrics", "name": "Kubernetes Clusters Total", "slide": "15", "desc": "Total Kubernetes clusters discovered", "default": ""},
    {"var": "K8S_1", "category": "Kubernetes", "name": "K8s Distribution #1", "slide": "15", "desc": "#1 Kubernetes distribution by cluster count (EKS/AKS/GKE/etc.)", "default": ""},
    {"var": "K8S_2", "category": "Kubernetes", "name": "K8s Distribution #2", "slide": "15", "desc": "#2 Kubernetes distribution by cluster count (EKS/AKS/GKE/etc.)", "default": ""},
    {"var": "K8S_3", "category": "Kubernetes", "name": "K8s Distribution #3", "slide": "15", "desc": "#3 Kubernetes distribution by cluster count (EKS/AKS/GKE/etc.)", "default": ""},
    {"var": "K8S_4", "category": "Kubernetes", "name": "K8s Distribution #4", "slide": "15", "desc": "#4 Kubernetes distribution by cluster count (EKS/AKS/GKE/etc.)", "default": ""},
    {"var": "K8S_5", "category": "Kubernetes", "name": "K8s Distribution #5", "slide": "15", "desc": "#5 Kubernetes distribution by cluster count (EKS/AKS/GKE/etc.)", "default": ""},
    {"var": "KC_CLI", "category": "Metrics", "name": "K8s Clusters w/ Sensor", "slide": "15", "desc": "Clusters with a Wiz sensor group installed", "default": ""},
    {"var": "KC_SE", "category": "Metrics", "name": "K8s Clusters w/ Audit Log Collector", "slide": "15", "desc": "Clusters with the Kubernetes audit log collector", "default": ""},
    {"var": "KG_IA", "category": "Metrics", "name": "K8s Clusters Internet-Exposed", "slide": "15", "desc": "Kubernetes clusters accessible from the internet", "default": ""},
    {"var": "OUT_DEP", "category": "Metrics", "name": "Outpost Deployments", "slide": "3", "desc": "Total Wiz Outpost deployments", "default": ""},
    {"var": "PC_TOT", "category": "Metrics", "name": "Sub-Projects (non-root)", "slide": "6", "desc": "Projects excluding the root project", "default": ""},
    {"var": "PI_T1_1", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #1 Name", "slide": "19", "desc": "Technology name of tier 1 potential integration #1 (by service-account activity)", "default": ""},
    {"var": "PI_T1_1_FA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #1 First Seen", "slide": "19", "desc": "First-added date for tier 1 potential integration #1", "default": ""},
    {"var": "PI_T1_1_LA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #1 Last Seen", "slide": "19", "desc": "Latest-added date for tier 1 potential integration #1", "default": ""},
    {"var": "PI_T1_1_SA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #1 Service Accounts", "slide": "19", "desc": "Service-account count for tier 1 potential integration #1", "default": ""},
    {"var": "PI_T1_2", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #2 Name", "slide": "19", "desc": "Technology name of tier 1 potential integration #2 (by service-account activity)", "default": ""},
    {"var": "PI_T1_2_FA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #2 First Seen", "slide": "19", "desc": "First-added date for tier 1 potential integration #2", "default": ""},
    {"var": "PI_T1_2_LA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #2 Last Seen", "slide": "19", "desc": "Latest-added date for tier 1 potential integration #2", "default": ""},
    {"var": "PI_T1_2_SA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #2 Service Accounts", "slide": "19", "desc": "Service-account count for tier 1 potential integration #2", "default": ""},
    {"var": "PI_T1_3", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #3 Name", "slide": "19", "desc": "Technology name of tier 1 potential integration #3 (by service-account activity)", "default": ""},
    {"var": "PI_T1_3_FA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #3 First Seen", "slide": "19", "desc": "First-added date for tier 1 potential integration #3", "default": ""},
    {"var": "PI_T1_3_LA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #3 Last Seen", "slide": "19", "desc": "Latest-added date for tier 1 potential integration #3", "default": ""},
    {"var": "PI_T1_3_SA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #3 Service Accounts", "slide": "19", "desc": "Service-account count for tier 1 potential integration #3", "default": ""},
    {"var": "PI_T1_4", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #4 Name", "slide": "19", "desc": "Technology name of tier 1 potential integration #4 (by service-account activity)", "default": ""},
    {"var": "PI_T1_4_FA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #4 First Seen", "slide": "19", "desc": "First-added date for tier 1 potential integration #4", "default": ""},
    {"var": "PI_T1_4_LA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #4 Last Seen", "slide": "19", "desc": "Latest-added date for tier 1 potential integration #4", "default": ""},
    {"var": "PI_T1_4_SA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #4 Service Accounts", "slide": "19", "desc": "Service-account count for tier 1 potential integration #4", "default": ""},
    {"var": "PI_T1_5", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #5 Name", "slide": "19", "desc": "Technology name of tier 1 potential integration #5 (by service-account activity)", "default": ""},
    {"var": "PI_T1_5_FA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #5 First Seen", "slide": "19", "desc": "First-added date for tier 1 potential integration #5", "default": ""},
    {"var": "PI_T1_5_LA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #5 Last Seen", "slide": "19", "desc": "Latest-added date for tier 1 potential integration #5", "default": ""},
    {"var": "PI_T1_5_SA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #5 Service Accounts", "slide": "19", "desc": "Service-account count for tier 1 potential integration #5", "default": ""},
    {"var": "PI_T1_6", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #6 Name", "slide": "19", "desc": "Technology name of tier 1 potential integration #6 (by service-account activity)", "default": ""},
    {"var": "PI_T1_6_FA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #6 First Seen", "slide": "19", "desc": "First-added date for tier 1 potential integration #6", "default": ""},
    {"var": "PI_T1_6_LA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #6 Last Seen", "slide": "19", "desc": "Latest-added date for tier 1 potential integration #6", "default": ""},
    {"var": "PI_T1_6_SA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #6 Service Accounts", "slide": "19", "desc": "Service-account count for tier 1 potential integration #6", "default": ""},
    {"var": "PI_T1_7", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #7 Name", "slide": "19", "desc": "Technology name of tier 1 potential integration #7 (by service-account activity)", "default": ""},
    {"var": "PI_T1_7_FA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #7 First Seen", "slide": "19", "desc": "First-added date for tier 1 potential integration #7", "default": ""},
    {"var": "PI_T1_7_LA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #7 Last Seen", "slide": "19", "desc": "Latest-added date for tier 1 potential integration #7", "default": ""},
    {"var": "PI_T1_7_SA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #7 Service Accounts", "slide": "19", "desc": "Service-account count for tier 1 potential integration #7", "default": ""},
    {"var": "PI_T1_8", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #8 Name", "slide": "19", "desc": "Technology name of tier 1 potential integration #8 (by service-account activity)", "default": ""},
    {"var": "PI_T1_8_FA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #8 First Seen", "slide": "19", "desc": "First-added date for tier 1 potential integration #8", "default": ""},
    {"var": "PI_T1_8_LA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #8 Last Seen", "slide": "19", "desc": "Latest-added date for tier 1 potential integration #8", "default": ""},
    {"var": "PI_T1_8_SA", "category": "Potential Integrations", "name": "Tier 1 Potential Integration #8 Service Accounts", "slide": "19", "desc": "Service-account count for tier 1 potential integration #8", "default": ""},
    {"var": "PI_T2_1", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #1 Name", "slide": "19", "desc": "Technology name of tier 2 potential integration #1 (by service-account activity)", "default": ""},
    {"var": "PI_T2_1_FA", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #1 First Seen", "slide": "19", "desc": "First-added date for tier 2 potential integration #1", "default": ""},
    {"var": "PI_T2_1_LA", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #1 Last Seen", "slide": "19", "desc": "Latest-added date for tier 2 potential integration #1", "default": ""},
    {"var": "PI_T2_1_SA", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #1 Service Accounts", "slide": "19", "desc": "Service-account count for tier 2 potential integration #1", "default": ""},
    {"var": "PI_T2_2", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #2 Name", "slide": "19", "desc": "Technology name of tier 2 potential integration #2 (by service-account activity)", "default": ""},
    {"var": "PI_T2_2_FA", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #2 First Seen", "slide": "19", "desc": "First-added date for tier 2 potential integration #2", "default": ""},
    {"var": "PI_T2_2_LA", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #2 Last Seen", "slide": "19", "desc": "Latest-added date for tier 2 potential integration #2", "default": ""},
    {"var": "PI_T2_2_SA", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #2 Service Accounts", "slide": "19", "desc": "Service-account count for tier 2 potential integration #2", "default": ""},
    {"var": "PI_T2_3", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #3 Name", "slide": "19", "desc": "Technology name of tier 2 potential integration #3 (by service-account activity)", "default": ""},
    {"var": "PI_T2_3_FA", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #3 First Seen", "slide": "19", "desc": "First-added date for tier 2 potential integration #3", "default": ""},
    {"var": "PI_T2_3_LA", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #3 Last Seen", "slide": "19", "desc": "Latest-added date for tier 2 potential integration #3", "default": ""},
    {"var": "PI_T2_3_SA", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #3 Service Accounts", "slide": "19", "desc": "Service-account count for tier 2 potential integration #3", "default": ""},
    {"var": "PI_T2_4", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #4 Name", "slide": "19", "desc": "Technology name of tier 2 potential integration #4 (by service-account activity)", "default": ""},
    {"var": "PI_T2_4_FA", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #4 First Seen", "slide": "19", "desc": "First-added date for tier 2 potential integration #4", "default": ""},
    {"var": "PI_T2_4_LA", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #4 Last Seen", "slide": "19", "desc": "Latest-added date for tier 2 potential integration #4", "default": ""},
    {"var": "PI_T2_4_SA", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #4 Service Accounts", "slide": "19", "desc": "Service-account count for tier 2 potential integration #4", "default": ""},
    {"var": "PI_T2_5", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #5 Name", "slide": "19", "desc": "Technology name of tier 2 potential integration #5 (by service-account activity)", "default": ""},
    {"var": "PI_T2_5_FA", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #5 First Seen", "slide": "19", "desc": "First-added date for tier 2 potential integration #5", "default": ""},
    {"var": "PI_T2_5_LA", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #5 Last Seen", "slide": "19", "desc": "Latest-added date for tier 2 potential integration #5", "default": ""},
    {"var": "PI_T2_5_SA", "category": "Potential Integrations", "name": "Tier 2 Potential Integration #5 Service Accounts", "slide": "19", "desc": "Service-account count for tier 2 potential integration #5", "default": ""},
    {"var": "PI_T3_1", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #1 Name", "slide": "19", "desc": "Technology name of tier 3 potential integration #1 (by service-account activity)", "default": ""},
    {"var": "PI_T3_1_FA", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #1 First Seen", "slide": "19", "desc": "First-added date for tier 3 potential integration #1", "default": ""},
    {"var": "PI_T3_1_LA", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #1 Last Seen", "slide": "19", "desc": "Latest-added date for tier 3 potential integration #1", "default": ""},
    {"var": "PI_T3_1_SA", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #1 Service Accounts", "slide": "19", "desc": "Service-account count for tier 3 potential integration #1", "default": ""},
    {"var": "PI_T3_2", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #2 Name", "slide": "19", "desc": "Technology name of tier 3 potential integration #2 (by service-account activity)", "default": ""},
    {"var": "PI_T3_2_FA", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #2 First Seen", "slide": "19", "desc": "First-added date for tier 3 potential integration #2", "default": ""},
    {"var": "PI_T3_2_LA", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #2 Last Seen", "slide": "19", "desc": "Latest-added date for tier 3 potential integration #2", "default": ""},
    {"var": "PI_T3_2_SA", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #2 Service Accounts", "slide": "19", "desc": "Service-account count for tier 3 potential integration #2", "default": ""},
    {"var": "PI_T3_3", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #3 Name", "slide": "19", "desc": "Technology name of tier 3 potential integration #3 (by service-account activity)", "default": ""},
    {"var": "PI_T3_3_FA", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #3 First Seen", "slide": "19", "desc": "First-added date for tier 3 potential integration #3", "default": ""},
    {"var": "PI_T3_3_LA", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #3 Last Seen", "slide": "19", "desc": "Latest-added date for tier 3 potential integration #3", "default": ""},
    {"var": "PI_T3_3_SA", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #3 Service Accounts", "slide": "19", "desc": "Service-account count for tier 3 potential integration #3", "default": ""},
    {"var": "PI_T3_4", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #4 Name", "slide": "19", "desc": "Technology name of tier 3 potential integration #4 (by service-account activity)", "default": ""},
    {"var": "PI_T3_4_FA", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #4 First Seen", "slide": "19", "desc": "First-added date for tier 3 potential integration #4", "default": ""},
    {"var": "PI_T3_4_LA", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #4 Last Seen", "slide": "19", "desc": "Latest-added date for tier 3 potential integration #4", "default": ""},
    {"var": "PI_T3_4_SA", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #4 Service Accounts", "slide": "19", "desc": "Service-account count for tier 3 potential integration #4", "default": ""},
    {"var": "PI_T3_5", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #5 Name", "slide": "19", "desc": "Technology name of tier 3 potential integration #5 (by service-account activity)", "default": ""},
    {"var": "PI_T3_5_FA", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #5 First Seen", "slide": "19", "desc": "First-added date for tier 3 potential integration #5", "default": ""},
    {"var": "PI_T3_5_LA", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #5 Last Seen", "slide": "19", "desc": "Latest-added date for tier 3 potential integration #5", "default": ""},
    {"var": "PI_T3_5_SA", "category": "Potential Integrations", "name": "Tier 3 Potential Integration #5 Service Accounts", "slide": "19", "desc": "Service-account count for tier 3 potential integration #5", "default": ""},
    {"var": "PRIVATE_BILLABLE", "category": "Preview Hub", "name": "Billable Private Previews", "slide": "8", "desc": "Bullet list of billable private-preview features enabled", "default": ""},
    {"var": "PRIVATE_NON_BILLABLE", "category": "Preview Hub", "name": "Non-Billable Private Previews", "slide": "8", "desc": "Bullet list of non-billable private-preview features enabled", "default": ""},
    {"var": "P_HBI", "category": "Metrics", "name": "High Business Impact Projects", "slide": "6", "desc": "Projects tagged High Business Impact", "default": ""},
    {"var": "P_LBI", "category": "Metrics", "name": "Low Business Impact Projects", "slide": "6", "desc": "Projects tagged Low Business Impact", "default": ""},
    {"var": "P_MBI", "category": "Metrics", "name": "Medium Business Impact Projects", "slide": "6", "desc": "Projects tagged Medium Business Impact", "default": ""},
    {"var": "P_TOT", "category": "Metrics", "name": "Total Projects", "slide": "6", "desc": "Total projects in the tenant", "default": ""},
    {"var": "RA_DAST", "category": "Metrics", "name": "Red Agent - DAST Attacker Findings", "slide": "4", "desc": "Open DAST Attacker findings from Red Agent", "default": ""},
    {"var": "RA_SI", "category": "Metrics", "name": "Red Agent - Secret Impact Findings", "slide": "4", "desc": "Open Secret Impact (blast radius) findings from Red Agent", "default": ""},
    {"var": "RA_TOTS", "category": "Metrics", "name": "Red Agent - Total Monthly Scans", "slide": "4", "desc": "Total Red Agent scans per month", "default": ""},
    {"var": "RA_WC", "category": "Metrics", "name": "Red Agent - Web Crawler Endpoints", "slide": "4", "desc": "AI-generated API endpoints found by the Red Agent web crawler", "default": ""},
    {"var": "RC_1", "category": "Container Registries", "name": "Registry Type #1 Count", "slide": "15", "desc": "Registry count for the #1 registry type", "default": ""},
    {"var": "RC_2", "category": "Container Registries", "name": "Registry Type #2 Count", "slide": "15", "desc": "Registry count for the #2 registry type", "default": ""},
    {"var": "RC_3", "category": "Container Registries", "name": "Registry Type #3 Count", "slide": "15", "desc": "Registry count for the #3 registry type", "default": ""},
    {"var": "RC_4", "category": "Container Registries", "name": "Registry Type #4 Count", "slide": "15", "desc": "Registry count for the #4 registry type", "default": ""},
    {"var": "RC_5", "category": "Container Registries", "name": "Registry Type #5 Count", "slide": "15", "desc": "Registry count for the #5 registry type", "default": ""},
    {"var": "RC_6", "category": "Container Registries", "name": "Registry Type #6 Count", "slide": "15", "desc": "Registry count for the #6 registry type", "default": ""},
    {"var": "ROADMAP_TRACKER", "category": "Metrics", "name": "Tracked Roadmap Items", "slide": "9", "desc": "Formatted list of tracked roadmap items", "default": ""},
    {"var": "R_1", "category": "Container Registries", "name": "Registry Type #1", "slide": "15", "desc": "#1 container registry type by count (ECR/ACR/GAR/etc.)", "default": ""},
    {"var": "R_2", "category": "Container Registries", "name": "Registry Type #2", "slide": "15", "desc": "#2 container registry type by count (ECR/ACR/GAR/etc.)", "default": ""},
    {"var": "R_3", "category": "Container Registries", "name": "Registry Type #3", "slide": "15", "desc": "#3 container registry type by count (ECR/ACR/GAR/etc.)", "default": ""},
    {"var": "R_4", "category": "Container Registries", "name": "Registry Type #4", "slide": "15", "desc": "#4 container registry type by count (ECR/ACR/GAR/etc.)", "default": ""},
    {"var": "R_5", "category": "Container Registries", "name": "Registry Type #5", "slide": "15", "desc": "#5 container registry type by count (ECR/ACR/GAR/etc.)", "default": ""},
    {"var": "R_6", "category": "Container Registries", "name": "Registry Type #6", "slide": "15", "desc": "#6 container registry type by count (ECR/ACR/GAR/etc.)", "default": ""},
    {"var": "R_AUT", "category": "Metrics", "name": "Registries - Auto-scanned", "slide": "15", "desc": "Container registries with automatic scanning", "default": ""},
    {"var": "R_CON", "category": "Metrics", "name": "Registries - Connector-based", "slide": "15", "desc": "Container registries scanned via a connector", "default": ""},
    {"var": "R_CUS", "category": "Metrics", "name": "Registries - Custom", "slide": "15", "desc": "Container registries with custom scanning configuration", "default": ""},
    {"var": "TI", "category": "Metrics", "name": "Total Container Images", "slide": "4, 15", "desc": "Total container images discovered", "default": ""},
    {"var": "U_ACT", "category": "Metrics", "name": "Active Users (30d)", "slide": "6", "desc": "Users who logged in within the last 30 days", "default": ""},
    {"var": "U_ENG", "category": "Metrics", "name": "User Engagement %", "slide": "6", "desc": "Active users as a percentage of total users", "default": ""},
    {"var": "U_RES", "category": "Metrics", "name": "Unscanned/Discovered Resources", "slide": "4", "desc": "Discovered resources pending full inventory", "default": ""},
    {"var": "U_TOT", "category": "Metrics", "name": "Total Users", "slide": "6", "desc": "Total non-deleted portal users", "default": ""},
    {"var": "VS_ARTIF", "category": "Vulnerability Scanner Config", "name": "Artifacts (lifecycle stages)", "slide": "18", "desc": "Lifecycle stages where build artifacts are analyzed", "default": ""},
    {"var": "VS_ARTIF_R", "category": "Vulnerability Scanner Config", "name": "Artifacts (lifecycle stages) - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Artifacts (lifecycle stages)", "default": ""},
    {"var": "VS_EOL", "category": "Vulnerability Scanner Config", "name": "End of Life Detection", "slide": "18", "desc": "End-of-life technology detection status/window", "default": ""},
    {"var": "VS_EOL_R", "category": "Vulnerability Scanner Config", "name": "End of Life Detection - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: End of Life Detection", "default": ""},
    {"var": "VS_EXCL", "category": "Vulnerability Scanner Config", "name": "Code Library Exclusion Paths (Legacy)", "slide": "18", "desc": "Whether legacy code-library exclusion paths are enabled", "default": ""},
    {"var": "VS_EXCL_R", "category": "Vulnerability Scanner Config", "name": "Code Library Exclusion Paths (Legacy) - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Code Library Exclusion Paths (Legacy)", "default": ""},
    {"var": "VS_GOSTD", "category": "Vulnerability Scanner Config", "name": "Go Standard Library", "slide": "18", "desc": "Whether Go standard library vulns are detected", "default": ""},
    {"var": "VS_GOSTD_R", "category": "Vulnerability Scanner Config", "name": "Go Standard Library - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Go Standard Library", "default": ""},
    {"var": "VS_GRADL", "category": "Vulnerability Scanner Config", "name": "Dependency Scopes: Gradle", "slide": "18", "desc": "Gradle dependency scopes analyzed", "default": ""},
    {"var": "VS_GRADL_R", "category": "Vulnerability Scanner Config", "name": "Dependency Scopes: Gradle - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Dependency Scopes: Gradle", "default": ""},
    {"var": "VS_JSDEP", "category": "Vulnerability Scanner Config", "name": "Dependency Scopes: JS (npm/pnpm/Yarn)", "slide": "18", "desc": "JS (npm/pnpm/Yarn) dependency scopes analyzed", "default": ""},
    {"var": "VS_JSDEP_R", "category": "Vulnerability Scanner Config", "name": "Dependency Scopes: JS (npm/pnpm/Yarn) - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Dependency Scopes: JS (npm/pnpm/Yarn)", "default": ""},
    {"var": "VS_LOCK", "category": "Vulnerability Scanner Config", "name": "Lock Files (lifecycle stages)", "slide": "18", "desc": "Lifecycle stages where lock files are analyzed", "default": ""},
    {"var": "VS_LOCK_R", "category": "Vulnerability Scanner Config", "name": "Lock Files (lifecycle stages) - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Lock Files (lifecycle stages)", "default": ""},
    {"var": "VS_LVULN", "category": "Vulnerability Scanner Config", "name": "Linux Vulnerabilities", "slide": "18", "desc": "Whether latest-kernel Linux vulnerabilities are detected", "default": ""},
    {"var": "VS_LVULN_R", "category": "Vulnerability Scanner Config", "name": "Linux Vulnerabilities - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Linux Vulnerabilities", "default": ""},
    {"var": "VS_MANIF", "category": "Vulnerability Scanner Config", "name": "Manifest Files (lifecycle stages)", "slide": "18", "desc": "Lifecycle stages where manifest files are analyzed", "default": ""},
    {"var": "VS_MANIF_R", "category": "Vulnerability Scanner Config", "name": "Manifest Files (lifecycle stages) - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Manifest Files (lifecycle stages)", "default": ""},
    {"var": "VS_MAVEN", "category": "Vulnerability Scanner Config", "name": "Dependency Scopes: Maven", "slide": "18", "desc": "Maven dependency scopes analyzed", "default": ""},
    {"var": "VS_MAVEN_R", "category": "Vulnerability Scanner Config", "name": "Dependency Scopes: Maven - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Dependency Scopes: Maven", "default": ""},
    {"var": "VS_OSPKG", "category": "Vulnerability Scanner Config", "name": "OS-Package Managed Code Libraries", "slide": "18", "desc": "Whether OS-package managed code library vulns are detected", "default": ""},
    {"var": "VS_OSPKG_R", "category": "Vulnerability Scanner Config", "name": "OS-Package Managed Code Libraries - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: OS-Package Managed Code Libraries", "default": ""},
    {"var": "VS_RHOS", "category": "Vulnerability Scanner Config", "name": "Ignore Red Hat OpenShift Vulns", "slide": "18", "desc": "Whether Red Hat OpenShift container library vulns are ignored", "default": ""},
    {"var": "VS_RHOS_R", "category": "Vulnerability Scanner Config", "name": "Ignore Red Hat OpenShift Vulns - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Ignore Red Hat OpenShift Vulns", "default": ""},
    {"var": "VS_WINB", "category": "Vulnerability Scanner Config", "name": "Windows App Bundled Libraries", "slide": "18", "desc": "Whether Windows app bundled library vulns are detected", "default": ""},
    {"var": "VS_WINB_R", "category": "Vulnerability Scanner Config", "name": "Windows App Bundled Libraries - Recommendation", "slide": "18", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Windows App Bundled Libraries", "default": ""},
    {"var": "WS_ADE1", "category": "Workload Scanner Config", "name": "ADE Private Endpoints (Disabled Public)", "slide": "17", "desc": "Workload scanner setting: ADE Private Endpoints (Disabled Public)", "default": ""},
    {"var": "WS_ADE1_R", "category": "Workload Scanner Config", "name": "ADE Private Endpoints (Disabled Public) - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: ADE Private Endpoints (Disabled Public)", "default": ""},
    {"var": "WS_ADE2", "category": "Workload Scanner Config", "name": "ADE Private Endpoints (Selected VNets)", "slide": "17", "desc": "Workload scanner setting: ADE Private Endpoints (Selected VNets)", "default": ""},
    {"var": "WS_ADE2_R", "category": "Workload Scanner Config", "name": "ADE Private Endpoints (Selected VNets) - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: ADE Private Endpoints (Selected VNets)", "default": ""},
    {"var": "WS_AFIM", "category": "Workload Scanner Config", "name": "Agentless File Integrity Monitoring", "slide": "17", "desc": "Workload scanner setting: Agentless File Integrity Monitoring", "default": ""},
    {"var": "WS_AFIM_R", "category": "Workload Scanner Config", "name": "Agentless File Integrity Monitoring - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Agentless File Integrity Monitoring", "default": ""},
    {"var": "WS_CIGS", "category": "Workload Scanner Config", "name": "Compute Instance Group Sampling", "slide": "17", "desc": "Workload scanner setting: Compute Instance Group Sampling", "default": ""},
    {"var": "WS_CIGS_R", "category": "Workload Scanner Config", "name": "Compute Instance Group Sampling - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Compute Instance Group Sampling", "default": ""},
    {"var": "WS_CMK", "category": "Workload Scanner Config", "name": "Shared AWS CMKs", "slide": "17", "desc": "Workload scanner setting: Shared AWS CMKs", "default": ""},
    {"var": "WS_CMK_R", "category": "Workload Scanner Config", "name": "Shared AWS CMKs - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Shared AWS CMKs", "default": ""},
    {"var": "WS_EXCL", "category": "Workload Scanner Config", "name": "Workload Scanning Exclusions", "slide": "17", "desc": "Workload scanner setting: Workload Scanning Exclusions", "default": ""},
    {"var": "WS_EXCL_R", "category": "Workload Scanner Config", "name": "Workload Scanning Exclusions - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Workload Scanning Exclusions", "default": ""},
    {"var": "WS_LAMB", "category": "Workload Scanner Config", "name": "AWS Lambda Version Scanning", "slide": "17", "desc": "Workload scanner setting: AWS Lambda Version Scanning", "default": ""},
    {"var": "WS_LAMB_R", "category": "Workload Scanner Config", "name": "AWS Lambda Version Scanning - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: AWS Lambda Version Scanning", "default": ""},
    {"var": "WS_LSAIL", "category": "Workload Scanner Config", "name": "AWS LightSail Scanning", "slide": "17", "desc": "Workload scanner setting: AWS LightSail Scanning", "default": ""},
    {"var": "WS_LSAIL_R", "category": "Workload Scanner Config", "name": "AWS LightSail Scanning - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: AWS LightSail Scanning", "default": ""},
    {"var": "WS_NONOS", "category": "Workload Scanner Config", "name": "Scanning Non-OS Disks", "slide": "17", "desc": "Workload scanner setting: Scanning Non-OS Disks", "default": ""},
    {"var": "WS_NONOS_R", "category": "Workload Scanner Config", "name": "Scanning Non-OS Disks - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Scanning Non-OS Disks", "default": ""},
    {"var": "WS_NRT", "category": "Workload Scanner Config", "name": "Near Real-Time Scanning", "slide": "17", "desc": "Workload scanner setting: Near Real-Time Scanning", "default": ""},
    {"var": "WS_NRTW", "category": "Workload Scanner Config", "name": "Include NRT Workload Scanning", "slide": "17", "desc": "Workload scanner setting: Include NRT Workload Scanning", "default": ""},
    {"var": "WS_NRTW_R", "category": "Workload Scanner Config", "name": "Include NRT Workload Scanning - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Include NRT Workload Scanning", "default": ""},
    {"var": "WS_NRT_R", "category": "Workload Scanner Config", "name": "Near Real-Time Scanning - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Near Real-Time Scanning", "default": ""},
    {"var": "WS_TAGS", "category": "Workload Scanner Config", "name": "Custom Scanner Tags", "slide": "17", "desc": "Workload scanner setting: Custom Scanner Tags", "default": ""},
    {"var": "WS_TAGS_R", "category": "Workload Scanner Config", "name": "Custom Scanner Tags - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Custom Scanner Tags", "default": ""},
    {"var": "WS_TVOL", "category": "Workload Scanner Config", "name": "AWS Scanning via Temp Volumes", "slide": "17", "desc": "Workload scanner setting: AWS Scanning via Temp Volumes", "default": ""},
    {"var": "WS_TVOL_R", "category": "Workload Scanner Config", "name": "AWS Scanning via Temp Volumes - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: AWS Scanning via Temp Volumes", "default": ""},
    {"var": "WS_VM", "category": "Workload Scanner Config", "name": "Virtual Machine Scanning", "slide": "17", "desc": "Workload scanner setting: Virtual Machine Scanning", "default": ""},
    {"var": "WS_VM_R", "category": "Workload Scanner Config", "name": "Virtual Machine Scanning - Recommendation", "slide": "17", "desc": "Best-practice indicator (✓ aligned / ✗ revisit / N/A) for: Virtual Machine Scanning", "default": ""},
]


def extract_template_tokens(template_path: str) -> set:
    """Return the set of distinct {{ }} tokens present in a .pptx deck template.

    Used to restrict the exported CSV to exactly the deck's variables. Returns an
    empty set (meaning 'no restriction') if the template cannot be read.
    """
    tokens = set()
    try:
        import zipfile
        with zipfile.ZipFile(template_path) as z:
            for name in z.namelist():
                if re.match(r"ppt/slides/slide\d+\.xml$", name):
                    xml = z.read(name).decode("utf-8", "replace")
                    tokens.update(re.findall(r"\{\{([A-Za-z0-9_]+)\}\}", xml))
    except Exception:
        return set()
    return tokens


def export_metrics_to_csv(
    variables: Dict[str, Any],
    output_path: str,
    customer_name: str = "Customer",
    template_tokens: Optional[set] = None,
) -> str:
    """
    Exports populated variables to a clean, well-formatted CSV file.
    Includes human-readable categories, metric titles, values, and slide locations.

    If ``template_tokens`` (the set of {{ }} tokens actually present in the deck
    template) is provided, the CSV is restricted to those variables so it lists
    exactly the deck's {{ }} variables and omits internal/intermediate helper keys.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    val_map = {}
    for k, v in variables.items():
        if isinstance(v, dict):
            val_map[k] = str(v.get("value", ""))
        else:
            val_map[k] = str(v if v is not None else "")

    rows = []
    seen_vars = set()

    for defn in METRIC_DEFINITIONS:
        var_key = defn["var"]
        seen_vars.add(var_key)
        # When restricting to the template, skip curated defs whose token is not in
        # the deck (keeps the CSV to exactly the deck's {{ }} variables).
        if template_tokens is not None and var_key not in template_tokens:
            continue
        val = val_map.get(var_key, defn.get("default", ""))
        rows.append({
            "Category": defn["category"],
            "Variable": f"{{{{{var_key}}}}}",
            "Metric Name": defn["name"],
            "Value": val,
            "Slide": defn["slide"],
            "Description": defn["desc"],
        })

    # Include remaining variables (e.g. Preview Hub, Scanner toggles, etc.)
    for k, v in sorted(val_map.items()):
        if k in seen_vars or k.startswith("_"):
            continue
        # With METRIC_DEFINITIONS now covering the full template, any remaining key is
        # an internal/intermediate helper. If we know the template tokens, drop keys
        # that are not actual {{ }} variables so the CSV stays clean and complete.
        if template_tokens is not None and k not in template_tokens:
            continue
        category = "Other"
        slide = "General"
        if k.startswith("PREVIEW_"):
            category = "Preview Hub"
            slide = "16-17"
        elif k.startswith("DSS_"):
            category = "Scanner Configurations"
            slide = "7-10"
        elif k.startswith("F_"):
            category = "Custom Frameworks"
            slide = "7"
        elif k.startswith("IA_") or k.startswith("IR_"):
            category = "Integrations Activity"
            slide = "15"
        
        rows.append({
            "Category": category,
            "Variable": f"{{{{{k}}}}}",
            "Metric Name": k.replace("_", " ").title(),
            "Value": v,
            "Slide": slide,
            "Description": f"Auto-extracted metric for {k}",
        })

    fieldnames = ["Category", "Variable", "Metric Name", "Value", "Slide", "Description"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return output_path


def generate_intake_template_csv(output_path: str) -> str:
    """
    Generates a blank customer intake CSV template with clear guidance
    for customers or TAMs to fill in values manually.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["Category", "Variable", "Metric Name", "Value", "Slide", "Description"]

    rows = []
    for defn in METRIC_DEFINITIONS:
        rows.append({
            "Category": defn["category"],
            "Variable": f"{{{{{defn['var']}}}}}",
            "Metric Name": defn["name"],
            "Value": "",  # Blank for customer to populate
            "Slide": defn["slide"],
            "Description": defn["desc"],
        })

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return output_path


def load_metrics_from_csv(csv_path: str) -> Dict[str, Dict[str, str]]:
    """
    Reads a customer-filled CSV file and extracts variables into a merged dictionary
    compatible with build_replacement_requests and PowerPoint / Google Slides builders.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Input CSV file not found: {csv_path}")

    merged = {}
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            var_raw = (row.get("Variable") or row.get("variable") or row.get("Token") or "").strip()
            val = (row.get("Value") or row.get("value") or "").strip()
            
            # Normalize token name (strip {{ and }})
            clean_var = re.sub(r'[\{\}\s]', '', var_raw)
            if not clean_var:
                continue

            merged[clean_var] = {
                "variable": clean_var,
                "value": val,
                "source": "CSV"
            }

    # Automatically compute missing scan coverage percentages if raw totals exist
    def auto_calc_pct(total_k, succ_k, fail_k, skip_k, pct_k):
        if pct_k not in merged or not merged[pct_k]["value"]:
            try:
                t = int(merged.get(total_k, {}).get("value", "0").replace(",", ""))
                s = int(merged.get(succ_k, {}).get("value", "0").replace(",", ""))
                f = int(merged.get(fail_k, {}).get("value", "0").replace(",", ""))
                sk = int(merged.get(skip_k, {}).get("value", "0").replace(",", ""))
                
                # If succeeded not given, infer as t - f - sk
                if s == 0 and t > 0:
                    s = max(0, t - f - sk)
                
                if t > 0:
                    pct = f"{int(math.floor(s / t * 100))}%"
                    merged[pct_k] = {"variable": pct_k, "value": pct, "source": "DERIVED_CSV"}
            except Exception:
                pass

    auto_calc_pct("NON_T", "NON_SUCC", "NON_F", "NON_S", "NON_C")
    auto_calc_pct("RCI_T", "RCI_SUCC", "RCI_F", "RCI_S", "RCI_C")
    auto_calc_pct("VMI_T", "VMI_SUCC", "VMI_F", "VMI_S", "VMI_C")
    auto_calc_pct("DS_T", "DS_SUCC", "DS_F", "DS_SK", "DS_P")

    return merged
