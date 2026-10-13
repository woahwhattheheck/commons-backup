output "commons_instance_id" {
  value = oci_core_instance.commons.id
}

output "commons_public_ip" {
  value = oci_core_instance.commons.public_ip
}

output "commons_data_volume_id" {
  value = oci_core_volume.commons_data.id
}

output "commons_capacity" {
  value = {
    shape         = "VM.Standard.A1.Flex"
    ocpus         = 2
    memory_gb     = 12
    boot_gb       = 50
    data_gb       = 150
    total_block_gb = 200
    data_mount    = "/srv/commons-cloud"
  }
}
