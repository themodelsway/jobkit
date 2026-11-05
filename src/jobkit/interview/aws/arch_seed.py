"""Seed topics for the architecture drill (generic, no personal data, no model answers).

`arch init` merges this into prep/arch/catalog.json. Everything AWS-specific lives in
src/aws/. Lifecycle facts and recent changes are NOT seeded: they are looked up on AWS pages and stored
with a source URL and a verified_on date by `arch refresh`.
"""
from __future__ import annotations

from typing import Final, NamedTuple

# Hosts accepted as a source for `arch refresh` (a specific page, not just the host)
SOURCE_HOSTS: Final[tuple[str, ...]] = ("aws.amazon.com", "docs.aws.amazon.com")

DIMENSIONS: Final[tuple[str, ...]] = (
    "What it is and the problem it solves",
    "When to choose it, and the alternatives (why not those)",
    "Key limits and gotchas",
    "Security (identity, encryption, network exposure)",
    "Cost drivers",
    "Scaling and failure behaviour (multi-AZ, regional limits, quotas)",
    "Where you have used it",
    "What changed in the last 3 years, and anything deprecated",
)

AREA_EDGE_NETWORKING: Final[str] = "Edge & Networking"
AREA_COMPUTE_CONTAINERS: Final[str] = "Compute & Containers"
AREA_STORAGE: Final[str] = "Storage"
AREA_DATABASES: Final[str] = "Databases"
AREA_INTEGRATION_ORCHESTRATION: Final[str] = "Integration & Orchestration"
AREA_SECURITY_IDENTITY: Final[str] = "Security & Identity"
AREA_OBSERVABILITY: Final[str] = "Observability"
AREA_GOVERNANCE_OPS: Final[str] = "Governance & Ops"
AREA_RESILIENCE: Final[str] = "Resilience"
AREA_ANALYTICS: Final[str] = "Analytics"
AREA_FINOPS: Final[str] = "FinOps"
AREA_GENAI: Final[str] = "GenAI"


class Service(NamedTuple):
    """A service card: area, name, tier (2 = core, 3 = optional) and alternative names used to find it in text."""

    area: str
    name: str
    tier: int
    aliases: tuple[str, ...] = ()


class Pair(NamedTuple):
    """A decision pair such as ALB vs NLB: the topic, the card name and the services being compared."""

    topic: str
    name: str
    members: tuple[str, ...]


# Tier 1 is never seeded: `arch init` promotes the services your resume mentions
# (or the list pinned with `profile tier1`).
SERVICES: Final[tuple[Service, ...]] = (
    # Edge & Networking
    Service(AREA_EDGE_NETWORKING, "CloudFront", 2, ("CDN", "OAC", "Origin Access Control")),
    Service(AREA_EDGE_NETWORKING, "Application Load Balancer", 2, ("ALB",)),
    Service(AREA_EDGE_NETWORKING, "Network Load Balancer", 2, ("NLB",)),
    Service(AREA_EDGE_NETWORKING, "API Gateway", 2, ("REST API", "HTTP API", "WebSocket API")),
    Service(AREA_EDGE_NETWORKING, "VPC", 2, ("subnet", "route table")),
    Service(AREA_EDGE_NETWORKING, "Security Groups", 2, ("NACL", "network ACL")),
    Service(AREA_EDGE_NETWORKING, "Transit Gateway", 2, ("TGW",)),
    Service(AREA_EDGE_NETWORKING, "Network Firewall", 2, ()),
    Service(AREA_EDGE_NETWORKING, "PrivateLink", 2, ()),
    Service(AREA_EDGE_NETWORKING, "Gateway VPC Endpoint", 2, ("gateway endpoint",)),
    Service(AREA_EDGE_NETWORKING, "Interface VPC Endpoint", 2, ("interface endpoint",)),
    Service(AREA_EDGE_NETWORKING, "Global Accelerator", 2, ()),
    Service(AREA_EDGE_NETWORKING, "Route 53", 2, ("hosted zone", "Route53")),
    Service(AREA_EDGE_NETWORKING, "WAF and Shield", 2, ("WAF", "Shield", "DDoS")),
    Service(AREA_EDGE_NETWORKING, "Gateway Load Balancer", 2, ("GWLB",)),
    Service(AREA_EDGE_NETWORKING, "NAT Gateway", 2, ("NAT",)),
    Service(AREA_EDGE_NETWORKING, "VPC Peering", 2, ("peering",)),
    Service(AREA_EDGE_NETWORKING, "Direct Connect and Site-to-Site VPN", 2, ("Direct Connect", "VPN")),
    Service(AREA_EDGE_NETWORKING, "VPC Lattice", 2, ("Lattice",)),
    Service(AREA_EDGE_NETWORKING, "VPC Flow Logs", 2, ("flow logs",)),
    # Compute & Containers
    Service(AREA_COMPUTE_CONTAINERS, "EC2", 2, ("Auto Scaling", "Graviton")),
    Service(AREA_COMPUTE_CONTAINERS, "ECS", 2, ("Elastic Container Service",)),
    Service(AREA_COMPUTE_CONTAINERS, "Fargate", 2, ()),
    Service(AREA_COMPUTE_CONTAINERS, "Lambda", 2, ("SnapStart", "provisioned concurrency")),
    Service(AREA_COMPUTE_CONTAINERS, "AWS Batch", 2, ("Batch",)),
    Service(AREA_COMPUTE_CONTAINERS, "EKS", 2, ("Kubernetes",)),
    Service(AREA_COMPUTE_CONTAINERS, "ECR", 2, ()),
    Service(AREA_COMPUTE_CONTAINERS, "App Runner", 3, ()),
    # Storage
    Service(AREA_STORAGE, "S3", 2, ("S3 Events", "S3 event notifications", "Object Lock", "lifecycle")),
    Service(AREA_STORAGE, "AWS Backup", 2, ("Backup",)),
    Service(AREA_STORAGE, "EBS", 2, ()),
    Service(AREA_STORAGE, "EFS", 2, ()),
    Service(AREA_STORAGE, "FSx", 2, ()),
    Service(AREA_STORAGE, "DataSync and Transfer Family", 3, ("DataSync", "Transfer Family")),
    # Databases
    Service(AREA_DATABASES, "RDS", 2, ("Relational Database Service",)),
    Service(AREA_DATABASES, "DynamoDB", 2, ("GSI", "DAX", "global tables")),
    Service(AREA_DATABASES, "ElastiCache for Valkey", 2, ("Valkey", "ElastiCache", "Redis")),
    Service(AREA_DATABASES, "OpenSearch Serverless", 2, ("OpenSearch",)),
    Service(AREA_DATABASES, "Aurora", 2, ("Aurora Serverless",)),
    Service(AREA_DATABASES, "RDS Proxy", 2, ()),
    Service(AREA_DATABASES, "DMS", 2, ("Database Migration Service",)),
    Service(AREA_DATABASES, "Redshift", 3, ()),
    # Integration & Orchestration
    Service(AREA_INTEGRATION_ORCHESTRATION, "Step Functions", 2, ("state machine",)),
    Service(AREA_INTEGRATION_ORCHESTRATION, "EventBridge", 2, ("CloudWatch Events",)),
    Service(AREA_INTEGRATION_ORCHESTRATION, "SNS", 2, ("Simple Notification Service",)),
    Service(AREA_INTEGRATION_ORCHESTRATION, "SES", 2, ("Simple Email Service",)),
    Service(AREA_INTEGRATION_ORCHESTRATION, "SQS", 2, ("queue", "DLQ")),
    Service(AREA_INTEGRATION_ORCHESTRATION, "Kinesis, MSK and Firehose", 2, ("Kinesis", "MSK", "Firehose", "Kafka")),
    Service(AREA_INTEGRATION_ORCHESTRATION, "AppSync", 3, ("GraphQL",)),
    Service(AREA_INTEGRATION_ORCHESTRATION, "EventBridge Pipes and Scheduler", 3, ("Pipes", "Scheduler")),
    # Security & Identity
    Service(AREA_SECURITY_IDENTITY, "IAM", 2, ("roles", "IAM role", "policy evaluation", "SCP", "permission boundary", "STS")),
    Service(AREA_SECURITY_IDENTITY, "Cognito", 2, ("user pool", "identity pool")),
    Service(AREA_SECURITY_IDENTITY, "KMS", 2, ("Key Management Service", "CMK")),
    Service(AREA_SECURITY_IDENTITY, "Secrets Manager", 2, ()),
    Service(AREA_SECURITY_IDENTITY, "Systems Manager Parameter Store", 2, ("Parameter Store", "SSM Parameter")),
    Service(AREA_SECURITY_IDENTITY, "CloudTrail", 2, ()),
    Service(AREA_SECURITY_IDENTITY, "Control Tower and Landing Zone", 2, ("Landing Zone", "Control Tower", "Organizations")),
    Service(AREA_SECURITY_IDENTITY, "IAM Identity Center", 2, ("SSO",)),
    Service(AREA_SECURITY_IDENTITY, "GuardDuty and Security Hub", 2, ("GuardDuty", "Security Hub")),
    Service(AREA_SECURITY_IDENTITY, "AWS Config", 2, ()),
    Service(AREA_SECURITY_IDENTITY, "Macie, Inspector and Access Analyzer", 3, ("Macie", "Inspector", "Access Analyzer")),
    Service(AREA_SECURITY_IDENTITY, "ACM", 2, ("Certificate Manager",)),
    Service(AREA_SECURITY_IDENTITY, "Simple AD", 3, ("Directory Service",)),
    # Observability
    Service(AREA_OBSERVABILITY, "CloudWatch Logs", 2, ("CloudWatch",)),
    Service(AREA_OBSERVABILITY, "CloudWatch metrics and alarms", 2, ("alarms", "metrics")),
    Service(AREA_OBSERVABILITY, "X-Ray and OpenTelemetry tracing", 2, ("X-Ray", "OpenTelemetry", "ADOT", "Application Signals", "Transaction Search", "tracing")),
    Service(AREA_OBSERVABILITY, "Managed Prometheus and Grafana", 3, ("Prometheus", "Grafana")),
    # Governance & Ops
    Service(AREA_GOVERNANCE_OPS, "Infrastructure as code", 2, ("CloudFormation", "CDK", "Terraform")),
    Service(AREA_GOVERNANCE_OPS, "Systems Manager", 2, ("Session Manager",)),
    Service(AREA_GOVERNANCE_OPS, "Well-Architected Framework", 2, ("Well-Architected",)),
    Service(AREA_GOVERNANCE_OPS, "Service Quotas", 3, ()),
    # Resilience
    Service(AREA_RESILIENCE, "Disaster recovery patterns", 2, ("RTO", "RPO", "pilot light", "warm standby", "DR")),
    Service(AREA_RESILIENCE, "Resilience Hub and Fault Injection", 3, ("Fault Injection", "chaos")),
    # Analytics
    Service(AREA_ANALYTICS, "Glue, Athena and Lake Formation", 3, ("Glue", "Athena", "Lake Formation")),
    # FinOps
    Service(AREA_FINOPS, "Savings Plans and Reserved Instances", 2, ("Savings Plans", "Reserved Instances", "RI")),
    Service(AREA_FINOPS, "Cost Explorer, Budgets and CUR", 2, ("Cost Explorer", "Budgets", "CUR", "Cost and Usage Report")),
    # GenAI
    Service(AREA_GENAI, "Bedrock", 2, ("Amazon Bedrock", "cross-region inference", "provisioned throughput")),
    Service(AREA_GENAI, "AgentCore", 2, ("Bedrock AgentCore", "AgentCore Runtime", "AgentCore Memory", "AgentCore Identity")),
    Service(AREA_GENAI, "AgentCore Gateway", 2, ("Agent Gateway", "AgentGateway", "MCP")),
    Service(AREA_GENAI, "Bedrock Guardrails", 2, ("Guardrails",)),
    Service(AREA_GENAI, "Bedrock Knowledge Bases", 2, ("Knowledge Bases", "RAG")),
    Service(AREA_GENAI, "Bedrock Agents (Classic)", 2, ("Bedrock Agents",)),
    Service(AREA_GENAI, "SageMaker", 2, ("SageMaker AI",)),
    Service(AREA_GENAI, "Vector stores", 3, ("S3 Vectors", "pgvector")),
    Service(AREA_GENAI, "Kendra and Q Business", 3, ("Kendra", "Q Business")),
)

PAIRS: Final[tuple[Pair, ...]] = (
    Pair("Load balancing and entry points", "ALB vs NLB vs API Gateway vs CloudFront", ("ALB", "NLB", "API Gateway", "CloudFront")),
    Pair("Compute", "ECS vs EKS vs Fargate vs Lambda vs EC2", ("ECS", "EKS", "Fargate", "Lambda", "EC2")),
    Pair("Messaging and orchestration", "Step Functions vs EventBridge vs SQS vs SNS", ("Step Functions", "EventBridge", "SQS", "SNS")),
    Pair("Data stores", "RDS/Aurora vs DynamoDB vs Valkey vs OpenSearch", ("RDS", "Aurora", "DynamoDB", "Valkey", "OpenSearch")),
    Pair("Secrets and keys", "Secrets Manager vs Parameter Store vs KMS", ("Secrets Manager", "Parameter Store", "KMS")),
    Pair("Private connectivity", "PrivateLink vs VPC peering vs Transit Gateway", ("PrivateLink", "peering", "Transit Gateway")),
    Pair("Private connectivity", "Gateway vs interface VPC endpoints", ("gateway endpoint", "interface endpoint")),
    Pair("Identity", "Cognito user pools vs identity pools", ("Cognito", "user pool", "identity pool")),
    Pair("Edge", "CloudFront vs Global Accelerator", ("CloudFront", "Global Accelerator")),
)

SCENARIOS: Final[tuple[str, ...]] = (
    "Design a three-tier web application (frontend, API, database) with high availability",
    "Design an event-driven data pipeline with retries, dead-letter handling and observability",
    "Design a RAG chatbot on Bedrock: ingestion, retrieval, guardrails, evaluation, cost control",
    "Design a multi-account landing zone with guardrails, logging and network segmentation",
    "Connect on-premises to AWS (hybrid): choices, resilience, DNS, security",
    "Disaster recovery for a critical workload: choose a pattern for given RTO/RPO",
    "Cost-optimization review of an existing AWS estate",
    "Secure a public API end to end (authn/z, WAF, throttling, secrets, logging)",
)
