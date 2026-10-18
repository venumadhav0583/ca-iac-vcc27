# CA-IaC placement annotations for the three evaluation workloads.
# Parsed by the Continuum Placement Resolver (cpr/) before `terraform plan`.

resource "aws_greengrass_component" "iot_ingest" {
  name = "iot-telemetry-ingest"

  continuum_placement {
    latency_budget_ms  = 30
    data_residency     = "any"
    compute_ms         = 1
    min_headroom       = 0.20
  }
}

resource "aws_outposts_service" "regional_compliance" {
  name = "regional-records-api"

  continuum_placement {
    latency_budget_ms  = 40
    data_residency     = "region"
    compute_ms         = 5
    min_headroom       = 0.20
  }
}

resource "aws_instance" "batch_ml" {
  name = "batch-ml-scoring"

  continuum_placement {
    latency_budget_ms  = 120
    data_residency     = "any"
    compute_ms         = 40
    min_headroom       = 0.20
  }
}
