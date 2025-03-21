from cloudshell.shell.core.driver_context import AutoLoadDetails

from cloudshell.cp.azure.actions.validation import ValidationActions


class AzureAutoloadFlow:
    def __init__(self, resource_config, azure_client, logger):
        """Init command.

        :param resource_config:
        :param azure_client:
        :param logging.Logger logger:
        """
        self._resource_config = resource_config
        self._azure_client = azure_client
        self._logger = logger

    def discover(self):
        validation_actions = ValidationActions(
            azure_client=self._azure_client, logger=self._logger
        )

        validation_actions.register_azure_providers()
        validation_actions.validate_azure_region(region=self._resource_config.region)
        validation_actions.validate_azure_mgmt_resource_group(
            mgmt_resource_group_name=self._resource_config.management_group_name,
        )

        validation_actions.validate_azure_sandbox_network(
            mgmt_resource_group_name=self._resource_config.management_group_name,
            sandbox_vnet_name=self._resource_config.sandbox_vnet_name,
        )

        if self._resource_config.management_vnet_name:
            validation_actions.validate_azure_mgmt_network(
                mgmt_resource_group_name=self._resource_config.management_group_name,
                mgmt_vnet_name=self._resource_config.management_vnet_name,
            )

        validation_actions.validate_azure_vm_size(
            vm_size=self._resource_config.vm_size, region=self._resource_config.region
        )

        validation_actions.validate_azure_additional_networks(
            mgmt_networks=self._resource_config.additional_mgmt_networks
        )

        validation_actions.validate_custom_tags(
            custom_tags=self._resource_config.custom_tags
        )

        return AutoLoadDetails([], [])
