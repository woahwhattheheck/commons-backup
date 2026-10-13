variable "tenancy_ocid" {
  description = "OCI tenancy that owns the Always Free home-region capacity."
  type        = string
}

variable "compartment_ocid" {
  description = "OCI compartment in which Commons resources are created."
  type        = string
}

variable "region" {
  description = "OCI home region; Always Free block volumes must remain here."
  type        = string
}
