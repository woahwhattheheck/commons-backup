terraform {
  required_version = ">= 1.5.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 6.0.0"
    }
  }
}

provider "oci" {
  region = var.region
}

data "oci_identity_availability_domains" "home" {
  compartment_id = var.tenancy_ocid
}

data "oci_core_images" "ubuntu_arm" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "24.04"
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

resource "oci_core_vcn" "commons" {
  compartment_id = var.compartment_ocid
  cidr_block     = "10.87.0.0/16"
  display_name   = "commons-always-free"
  dns_label      = "commonsfree"
}

resource "oci_core_internet_gateway" "commons" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.commons.id
  display_name   = "commons-always-free"
  enabled        = true
}

resource "oci_core_route_table" "commons" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.commons.id
  display_name   = "commons-always-free"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.commons.id
  }
}

resource "oci_core_security_list" "commons" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.commons.id
  display_name   = "commons-always-free-outbound"

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }
}

resource "oci_core_subnet" "commons" {
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.commons.id
  cidr_block        = "10.87.1.0/24"
  display_name      = "commons-always-free"
  dns_label         = "commons"
  route_table_id    = oci_core_route_table.commons.id
  security_list_ids = [oci_core_security_list.commons.id]
}

resource "oci_core_instance" "commons" {
  availability_domain = data.oci_identity_availability_domains.home.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  display_name        = "commons-always-free"
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    ocpus         = 2
    memory_in_gbs = 12
  }

  create_vnic_details {
    assign_public_ip = true
    subnet_id        = oci_core_subnet.commons.id
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu_arm.images[0].id
    boot_volume_size_in_gbs = 50
  }

  metadata = {
    user_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {}))
  }

  freeform_tags = {
    commons_route = "cloud-storage-only"
    lifecycle     = "copy-only"
  }
}

resource "oci_core_volume" "commons_data" {
  availability_domain = oci_core_instance.commons.availability_domain
  compartment_id      = var.compartment_ocid
  display_name        = "commons-always-free-data"
  size_in_gbs         = 150

  freeform_tags = {
    commons_route = "cloud-storage-only"
    lifecycle     = "copy-only"
  }
}

resource "oci_core_volume_attachment" "commons_data" {
  attachment_type = "paravirtualized"
  instance_id     = oci_core_instance.commons.id
  volume_id       = oci_core_volume.commons_data.id
  device          = "/dev/oracleoci/oraclevdb"
  display_name    = "commons-always-free-data"
}
