import re

from cloudshell.cp.azure.utils.rollback import RollbackCommand


class CreateAllowVMInboundPortRuleCommand(RollbackCommand):
    """Open traffic to VM on inbound ports (an attribute on the App) on the VM NSG."""

    NSG_RULE_PRIORITY = 1000
    NSG_RULE_NAME_TPL = "{vm_name}_inbound_port:{port_range}:{protocol}"

    def __init__(
        self,
        rollback_manager,
        cancellation_manager,
        nsg_actions,
        nsg_name: str,
        vm_name: str,
        inbound_port,
        resource_group_name: str,
        rules_priority_generator,
    ):
        """Init command."""
        super().__init__(
            rollback_manager=rollback_manager, cancellation_manager=cancellation_manager
        )
        self._nsg_actions = nsg_actions
        self._nsg_name = nsg_name
        self._vm_name = vm_name
        self._inbound_port = inbound_port
        self._resource_group_name = resource_group_name
        self._rules_priority_generator = rules_priority_generator
        self._port_range, self._protocol = self._parse_port_range(self._inbound_port)

    def _execute(self):
        self._nsg_actions.create_nsg_allow_rule(
            rule_name=self.NSG_RULE_NAME_TPL.format(
                vm_name=self._vm_name,
                port_range=self._port_range,
                protocol=self._protocol,
            ),
            resource_group_name=self._resource_group_name,
            nsg_name=self._nsg_name,
            dst_port_range=self._port_range,
            protocol=self._protocol,
            rule_priority=self._rules_priority_generator.get_priority(
                start_from=self.NSG_RULE_PRIORITY
            ),
        )

    def _parse_port_range(self, port_data):
        # todo: refactor this method !!!
        from_port = "from_port"
        to_port = "to_port"
        protocol = "protocol"
        tcp = "tcp"

        from_to_protocol_match = re.match(
            r"^((?P<from_port>\d+)-(?P<to_port>\d+):(?P<protocol>(udp|tcp)))$",
            port_data,
            flags=re.IGNORECASE,
        )

        # 80-50000:udp
        if from_to_protocol_match:
            from_port = from_to_protocol_match.group(from_port)
            to_port = from_to_protocol_match.group(to_port)
            protocol = from_to_protocol_match.group(protocol).lower()

            return f"{from_port}-{to_port}", protocol

        from_protocol_match = re.match(
            r"^((?P<from_port>\d+):(?P<protocol>(udp|tcp)))$",
            port_data,
            flags=re.IGNORECASE,
        )

        # 80:udp
        if from_protocol_match:
            port = from_protocol_match.group(from_port)
            protocol = from_protocol_match.group(protocol).lower()
            return port, protocol

        from_to_match = re.match(r"^((?P<from_port>\d+)-(?P<to_port>\d+))$", port_data)

        # 20-80
        if from_to_match:
            from_port = from_to_match.group(from_port)
            to_port = from_to_match.group(to_port)
            protocol = tcp

            return f"{from_port}-{to_port}", protocol

        port_match = re.match(r"^((?P<from_port>\d+))$", port_data)
        # 80
        if port_match:
            port = port_match.group(from_port)
            protocol = tcp

            return port, protocol

        raise Exception(f"Value '{port_data}' is not a valid port rule")

    def rollback(self):
        self._nsg_actions.delete_nsg_rule(
            rule_name=self.NSG_RULE_NAME_TPL.format(
                vm_name=self._vm_name,
                port_range=self._port_range,
                protocol=self._protocol,
            ),
            resource_group_name=self._resource_group_name,
            nsg_name=self._nsg_name,
        )
