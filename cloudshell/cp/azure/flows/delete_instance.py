from functools import partial
from http import HTTPStatus

from msrestazure.azure_exceptions import CloudError

from cloudshell.cp.azure.actions.network import NetworkActions
from cloudshell.cp.azure.actions.network_security_group import (
    NetworkSecurityGroupActions,
)
from cloudshell.cp.azure.actions.storage_account import StorageAccountActions
from cloudshell.cp.azure.actions.vm import VMActions
from cloudshell.cp.azure.utils.azure_name_parser import get_name_from_resource_id


class AzureDeleteInstanceFlow:
    def __init__(
        self,
        resource_config,
        azure_client,
        reservation_info,
        cs_ip_pool_manager,
        lock_manager,
        logger,
    ):
        """Init command.

        :param resource_config:
        :param azure_client:
        :param reservation_info:
        :param cs_ip_pool_manager:
        :param lock_manager:
        :param logging.Logger logger:
        """
        self._resource_config = resource_config
        self._azure_client = azure_client
        self._reservation_info = reservation_info
        self._cs_ip_pool_manager = cs_ip_pool_manager
        self._lock_manager = lock_manager
        self._logger = logger

    def _get_public_ip_names(self, network_interfaces):
        """Get public IP addresses names for the provided interfaces.

        :param network_interfaces:
        :return:
        """
        public_ip_names = []
        for interface in network_interfaces:
            public_ip = interface.ip_configurations[0].public_ip_address

            if public_ip is not None:
                public_ip_name = get_name_from_resource_id(public_ip.id)
                public_ip_names.append(public_ip_name)

        return public_ip_names

    def _get_private_ip_adresses(self, network_interfaces, network_actions):
        """Get private IP addresses for the provided interfaces.

        :param network_interfaces:
        :return:
        """
        private_ip_names = []
        for interface in network_interfaces:
            ip_config = interface.ip_configurations[0]

            if network_actions.is_static_ip_allocation_type(
                ip_type=ip_config.private_ip_allocation_method
            ):
                private_ip_names.append(ip_config.private_ip_address)

        return private_ip_names

    def _delete_vm_disk(self, vm, resource_group_name):
        """Delete the VM data disk. Will delete VHD or Managed Disk of the VM.

        :param azure.mgmt.compute.models.VirtualMachine vm:
        :param str resource_group_name:
        :return:
        """
        storage_actions = StorageAccountActions(
            azure_client=self._azure_client, logger=self._logger
        )

        if vm.storage_profile.os_disk.vhd:
            storage_actions.delete_vhd_disk(
                vhd_url=vm.storage_profile.os_disk.vhd.url,
                resource_group_name=resource_group_name,
            )

        elif vm.storage_profile.os_disk.managed_disk:
            storage_actions.delete_disk(
                disk_name=vm.storage_profile.os_disk.name,
                resource_group_name=resource_group_name,
            )
        else:
            raise Exception(
                f"Unable to delete data disk under VM {vm.name}. "
                f"Unsupported OS data disk type"
            )

    def delete_instance(self, deployed_app):
        """Delete VM instance.

        :param deployed_app:
        :return:
        """
        sandbox_resource_group_name = self._reservation_info.get_resource_group_name()
        vm_resource_group_name = (
            deployed_app.resource_group_name or sandbox_resource_group_name
        )
        nsg_name = self._reservation_info.get_network_security_group_name()

        vm_actions = VMActions(azure_client=self._azure_client, logger=self._logger)
        network_actions = NetworkActions(
            azure_client=self._azure_client, logger=self._logger
        )
        nsg_actions = NetworkSecurityGroupActions(
            azure_client=self._azure_client, logger=self._logger
        )
        storage_actions = StorageAccountActions(
            azure_client=self._azure_client, logger=self._logger
        )
        try:
            vm = vm_actions.get_vm(
                vm_name=deployed_app.name, resource_group_name=vm_resource_group_name
            )
        except CloudError:
            return

        network_interface_names = [
            get_name_from_resource_id(interface.id)
            for interface in vm.network_profile.network_interfaces
        ]

        network_interfaces = [
            network_actions.get_vm_network(
                interface_name=interface_name,
                resource_group_name=vm_resource_group_name,
            )
            for interface_name in network_interface_names
        ]

        public_ip_names = self._get_public_ip_names(
            network_interfaces=network_interfaces
        )

        private_ips = self._get_private_ip_adresses(
            network_interfaces=network_interfaces, network_actions=network_actions
        )

        delete_commands = [
            partial(
                vm_actions.delete_vm,
                vm_name=deployed_app.name,
                resource_group_name=vm_resource_group_name,
            )
        ]

        for interface_name in network_interface_names:
            delete_commands.append(
                partial(
                    network_actions.delete_vm_network,
                    interface_name=interface_name,
                    resource_group_name=vm_resource_group_name,
                )
            )

        for public_ip_name in public_ip_names:
            delete_commands.append(
                partial(
                    network_actions.delete_public_ip,
                    public_ip_name=public_ip_name,
                    resource_group_name=vm_resource_group_name,
                )
            )

        delete_commands.append(
            partial(
                self._delete_vm_disk, vm=vm, resource_group_name=vm_resource_group_name
            )
        )

        for data_disk in vm.storage_profile.data_disks:
            delete_commands.append(
                partial(
                    storage_actions.delete_disk,
                    disk_name=data_disk.name,
                    resource_group_name=vm_resource_group_name,
                )
            )

        delete_commands.append(
            partial(
                nsg_actions.delete_vm_network_security_group,
                vm_name=vm.name,
                resource_group_name=vm_resource_group_name,
            )
        )

        if nsg_actions.network_security_group_exists(
            nsg_name=nsg_name, resource_group_name=sandbox_resource_group_name
        ):
            for nsg_rule in nsg_actions.get_nsg_rules(
                nsg_name=nsg_name, resource_group_name=sandbox_resource_group_name
            ):
                delete_commands.append(
                    partial(
                        nsg_actions.delete_nsg_rule,
                        rule_name=nsg_rule.name,
                        nsg_name=nsg_name,
                        resource_group_name=sandbox_resource_group_name,
                    )
                )

        for delete_command in delete_commands:
            try:
                delete_command()
            except CloudError as e:
                if e.status_code == HTTPStatus.NOT_FOUND:
                    self._logger.warning(
                        "Unable to find resource on Azure for deleting:", exc_info=True
                    )
                    continue
                raise

        if private_ips:
            try:
                self._cs_ip_pool_manager.release_ips(
                    reservation_id=self._reservation_info.reservation_id,
                    ips=private_ips,
                )
            except Exception:
                self._logger.warning(
                    f"Unable to release private IPs {private_ips} from the CloudShell:",
                    exc_info=True,
                )

        vm_nsg_name = nsg_actions.prepare_vm_nsg_name(vm_name=deployed_app.name)
        self._lock_manager.remove_lock(vm_nsg_name)
